import { ControlRegistry } from "./ui/registry.js";
import {
  BALANCE_COMPONENT,
  BALANCE_SLIDER_PRESENTATION,
  EQ_COMPONENT,
  EQ_FADER_PRESENTATION,
  FADER_LADDER_PRESENTATION,
  LED_METERS_PRESENTATION,
  METADATA_COMPONENT,
  METERS_COMPONENT,
  NOW_PLAYING_PRESENTATION,
  PRESETS_COMPONENT,
  PRESET_SELECTOR_PRESENTATION,
  SPECTRUM_COMPONENT,
  SPECTRUM_OVERLAY_PRESENTATION,
  TONE_BANK_COMPONENT,
  registerBuiltins,
} from "./ui/builtins.js";

const equalizer = document.querySelector("#equalizer");
const engineStatus = document.querySelector("#engine-status");
const message = document.querySelector("#message");
const themeList = document.querySelector("#theme-list");
const themeStylesheet = document.querySelector("#theme-stylesheet");
const balanceRoot = document.querySelector("#balance-control");
const metersRoot = document.querySelector("#stereo-meter-control");
const spectrumRoot = document.querySelector("#spectrum-control");
const metadataRoot = document.querySelector("#metadata-control");
const presetsRoot = document.querySelector("#preset-component");
const receiverLayout = document.querySelector("#receiver-layout");
const layoutSurfaces = new Map(
  [...receiverLayout.querySelectorAll("[data-layout-surface]")].map((surface) => [
    surface.dataset.layoutSurface,
    surface,
  ]),
);

let bands = {};
let balance = 0;
let updateTimer;
let balanceTimer;
let eventSocket;
let reconnectTimer;
let currentMetadata = {};
let currentTransport = {};
let presetItems = [];
let activePreset = null;
let selectedPreset = null;
let eqControl;
let balanceControl;
let metersControl;
let spectrumControl;
let metadataControl;
let presetsControl;
let toneBankControl;
const controls = new ControlRegistry();
registerBuiltins(controls);
let currentState;
let activeTheme;

const DEFAULT_REGIONS = {
  [EQ_COMPONENT]: {
    id: "tone",
    component: EQ_COMPONENT,
    presentation: EQ_FADER_PRESENTATION,
    options: { orientation: "responsive" },
  },
  [BALANCE_COMPONENT]: {
    id: "balance",
    component: BALANCE_COMPONENT,
    presentation: BALANCE_SLIDER_PRESENTATION,
    options: {},
  },
  [METERS_COMPONENT]: {
    id: "meters",
    component: METERS_COMPONENT,
    presentation: LED_METERS_PRESENTATION,
    options: { releasePerFrame: 0.7 },
  },
  [SPECTRUM_COMPONENT]: {
    id: "spectrum",
    component: SPECTRUM_COMPONENT,
    presentation: SPECTRUM_OVERLAY_PRESENTATION,
    options: {},
  },
  [TONE_BANK_COMPONENT]: {
    id: "tone-bank",
    component: TONE_BANK_COMPONENT,
    presentation: FADER_LADDER_PRESENTATION,
    options: { orientation: "responsive", segments: 24 },
  },
  [METADATA_COMPONENT]: {
    id: "now-playing",
    component: METADATA_COMPONENT,
    presentation: NOW_PLAYING_PRESENTATION,
    options: {},
  },
  [PRESETS_COMPONENT]: {
    id: "presets",
    component: PRESETS_COMPONENT,
    presentation: PRESET_SELECTOR_PRESENTATION,
    options: {},
  },
};

const TOKEN_PROPERTIES = {
  "receiver.faceplate": "--receiver-faceplate",
  "receiver.panel": "--receiver-panel",
  "receiver.glass": "--receiver-glass",
  "receiver.legend": "--receiver-legend",
  "receiver.led": "--receiver-led",
  "receiver.meter.normal": "--receiver-meter-normal",
  "receiver.meter.hot": "--receiver-meter-hot",
  "receiver.accent": "--receiver-accent",
};
const DEFAULT_SURFACE_FLOW = ["levels", "tone", "presets"];

const labelFrequency = (frequency) =>
  frequency >= 1000 ? `${frequency / 1000}k` : `${frequency}`;

const labelGain = (gain) => `${gain > 0 ? "+" : ""}${gain.toFixed(1)} dB`;
const labelBalance = (value) => {
  if (value === 0) return "Center";
  return `${value < 0 ? "L" : "R"} ${Math.abs(value)}`;
};

function showMessage(text, error = false) {
  message.textContent = text;
  message.classList.toggle("error", error);
}

async function initializeThemes() {
  const themes = await request("/api/v1/themes");
  themeList.replaceChildren(
    ...themes.map((theme) => {
      const option = document.createElement("option");
      option.value = theme.id;
      option.textContent = theme.name;
      option.dataset.stylesheet = theme.stylesheet;
      return option;
    }),
  );
  const saved = localStorage.getItem("coldth-theme");
  themeList.value = themes.some((theme) => theme.id === saved)
    ? saved
    : "original-yellow";
  return loadTheme(themeList.value);
}

function applyThemeDescriptor(descriptor) {
  const option = themeList.selectedOptions[0];
  if (!option || descriptor.id !== option.value) return;
  const stylesheets = descriptor.stylesheets || [descriptor.stylesheet];
  document
    .querySelectorAll('link[data-inherited-theme-stylesheet="true"]')
    .forEach((link) => link.remove());
  themeStylesheet.href = stylesheets[0];
  let previousStylesheet = themeStylesheet;
  for (const href of stylesheets.slice(1)) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.dataset.inheritedThemeStylesheet = "true";
    previousStylesheet.after(link);
    previousStylesheet = link;
  }
  document.documentElement.dataset.theme = descriptor.id;
  for (const property of Object.values(TOKEN_PROPERTIES)) {
    document.documentElement.style.removeProperty(property);
  }
  for (const [token, value] of Object.entries(descriptor.tokens || {})) {
    const property = TOKEN_PROPERTIES[token];
    if (property) document.documentElement.style.setProperty(property, value);
  }
  localStorage.setItem("coldth-theme", descriptor.id);
  activeTheme = descriptor;
}

async function loadTheme(themeId) {
  const descriptor = await request(
    `/api/v1/themes/${encodeURIComponent(themeId)}`,
  );
  applyThemeDescriptor(descriptor);
  return descriptor;
}

themeList.addEventListener("change", async () => {
  try {
    const descriptor = await loadTheme(themeList.value);
    if (currentState) mountControls(currentState, descriptor);
  } catch (error) {
    showMessage(`Could not activate theme: ${error.message}`, true);
  }
});

function setEngineStatus(engine) {
  engineStatus.classList.toggle("online", engine.online);
  engineStatus.lastChild.textContent = engine.online
    ? " Audio online"
    : " Audio offline";
  engineStatus.title = engine.error || "CamillaDSP is running";
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      detail = (await response.json()).detail || detail;
    } catch (_) {
      // Keep the HTTP error.
    }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

function levelPercent(db) {
  return Math.max(0, Math.min(100, ((Number(db) + 60) / 60) * 100));
}

function formatLevel(db) {
  return Number.isFinite(Number(db)) && Number(db) > -60
    ? `${Number(db).toFixed(1)}`
    : "−∞";
}

function connectEvents() {
  clearTimeout(reconnectTimer);
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  eventSocket = new WebSocket(`${protocol}//${location.host}/api/v1/events`);
  eventSocket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "state.snapshot") {
      currentMetadata = payload.data.metadata || {};
      currentTransport = payload.data.transport || {};
      applyTone(payload.data.tone);
      metadataControl?.setValue({
        metadata: currentMetadata,
        transport: currentTransport,
      });
    } else if (payload.type === "meter.frame") {
      metersControl?.setValue(payload.data);
      spectrumControl?.setValue(payload.data.spectrum);
      toneBankControl?.setValue({ spectrum: payload.data.spectrum });
    } else if (payload.type === "metadata.changed") {
      currentMetadata = payload.data;
      metadataControl?.setValue({
        metadata: currentMetadata,
        transport: currentTransport,
      });
    } else if (payload.type === "transport.changed") {
      currentTransport = payload.data;
      metadataControl?.setValue({
        metadata: currentMetadata,
        transport: currentTransport,
      });
    } else if (payload.type === "tone.changed") {
      applyTone(payload.data);
    } else if (payload.type === "preset.loaded") {
      applyTone(payload.data.tone);
      refreshPresets(payload.data.preset.name);
    } else if (
      ["preset.saved", "preset.imported", "preset.deleted"].includes(payload.type)
    ) {
      refreshPresets();
    }
  });
  eventSocket.addEventListener("close", () => {
    metersControl?.setValue(null);
    spectrumControl?.setValue(null);
    toneBankControl?.setValue({ spectrum: null });
    reconnectTimer = setTimeout(connectEvents, 2000);
  });
  eventSocket.addEventListener("error", () => eventSocket.close());
}

function applyTone(tone = {}) {
  if (tone.bands) {
    bands = tone.bands;
    eqControl?.setValue(bands);
    toneBankControl?.setValue({ bands });
  }
  if (tone.balance !== undefined) {
    balance = tone.balance;
    balanceControl?.setValue(balance);
  }
  if ("preset" in tone) {
    activePreset = tone.preset;
    if (activePreset) selectedPreset = activePreset;
    presetsControl?.setValue({ presets: presetItems, selected: selectedPreset });
  }
}

function scheduleUpdate() {
  clearTimeout(updateTimer);
  updateTimer = setTimeout(async () => {
    try {
      const result = await request("/api/v1/tone/eq", {
        method: "PUT",
        body: JSON.stringify({ bands }),
      });
      setEngineStatus(result.engine);
      showMessage(
        result.applied
          ? "EQ applied"
          : `Saved; audio update failed: ${
              result.engine.apply_error || result.engine.error || "unknown error"
            }`,
        !result.applied,
      );
    } catch (error) {
      showMessage(error.message, true);
    }
  }, 120);
}

function scheduleBalanceUpdate() {
  clearTimeout(balanceTimer);
  balanceTimer = setTimeout(async () => {
    try {
      const result = await request("/api/v1/tone/balance", {
        method: "PUT",
        body: JSON.stringify({ balance }),
      });
      setEngineStatus(result.engine);
      showMessage(result.applied ? "Balance applied" : "Balance saved", !result.applied);
    } catch (error) {
      showMessage(error.message, true);
    }
  }, 120);
}

async function refreshPresets(selected) {
  presetItems = await request("/api/v1/presets");
  if (selected !== undefined) selectedPreset = selected;
  presetsControl?.setValue({ presets: presetItems, selected: selectedPreset });
}

async function runPresetAction(action) {
  try {
    await action();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function savePreset(name) {
  const result = await request("/api/v1/presets", {
    method: "POST",
    body: JSON.stringify({ name, bands }),
  });
  await refreshPresets(result.preset.name);
  showMessage(`Saved “${result.preset.name}”`);
}

async function loadPreset(name) {
  const result = await request(
    `/api/v1/presets/${encodeURIComponent(name)}/load`,
    { method: "POST" },
  );
  applyTone(result.tone);
  setEngineStatus(result.engine);
  await refreshPresets(name);
  showMessage(`Loaded “${name}”`);
}

async function exportPreset(name) {
  const preset = await request(
    `/api/v1/presets/${encodeURIComponent(name)}/export`,
  );
  const blob = new Blob([`${JSON.stringify(preset, null, 2)}\n`], {
    type: "application/json",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${preset.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

async function deletePreset(name) {
  await request(`/api/v1/presets/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  await refreshPresets(null);
  showMessage(`Deleted “${name}”`);
}

async function importPreset(file) {
  const result = await request("/api/v1/presets/import", {
    method: "POST",
    body: await file.text(),
  });
  await refreshPresets(result.preset.name);
  showMessage(`Imported “${result.preset.name}”`);
}

function activeRegions(descriptor) {
  const declared = activeLayout(descriptor)?.regions || [];
  const regions = { ...DEFAULT_REGIONS };
  for (const region of declared) regions[region.component] = region;
  return regions;
}

function activeLayout(descriptor) {
  const orientation = matchMedia("(orientation: portrait)").matches
    ? "portrait"
    : "landscape";
  return descriptor?.layouts?.[orientation] || null;
}

function applySurfaceFlow(descriptor) {
  const requested = activeLayout(descriptor)?.flow || [];
  const flow = [
    ...requested,
    ...DEFAULT_SURFACE_FLOW.filter((surface) => !requested.includes(surface)),
  ];
  for (const surface of flow) {
    const element = layoutSurfaces.get(surface);
    if (element) receiverLayout.append(element);
  }
  receiverLayout.dataset.flow = flow.join(" ");
}

function disposeControls() {
  for (const control of [
    spectrumControl,
    presetsControl,
    metadataControl,
    metersControl,
    balanceControl,
    eqControl,
    toneBankControl,
  ]) {
    control?.dispose?.();
  }
}

function mountControls(state, descriptor) {
  disposeControls();
  applySurfaceFlow(descriptor);
  const regions = activeRegions(descriptor);
  const usesToneBank = Boolean(
    activeLayout(descriptor)?.regions?.some(
      (region) => region.component === TONE_BANK_COMPONENT,
    ),
  );
  for (const [component, root] of [
    [EQ_COMPONENT, equalizer],
    [BALANCE_COMPONENT, balanceRoot],
    [METERS_COMPONENT, metersRoot],
    [SPECTRUM_COMPONENT, spectrumRoot],
    [METADATA_COMPONENT, metadataRoot],
    [PRESETS_COMPONENT, presetsRoot],
  ]) {
    root.dataset.themeRegion = regions[component].id;
  }

  eqControl = null;
  spectrumControl = null;
  toneBankControl = null;
  spectrumRoot.hidden = usesToneBank;
  if (usesToneBank) {
    equalizer.dataset.themeRegion = regions[TONE_BANK_COMPONENT].id;
    toneBankControl = controls.mount({
      ...regions[TONE_BANK_COMPONENT],
      root: equalizer,
      context: {
        value: bands,
        frequencies: state.limits.eq.frequencies,
        range: state.limits.eq,
        labelFrequency,
        labelValue: labelGain,
        levelPercent,
        onInput(nextBands) {
          bands = nextBands;
          scheduleUpdate();
        },
      },
    });
  } else {
    eqControl = controls.mount({
      ...regions[EQ_COMPONENT],
      root: equalizer,
      context: {
        value: bands,
        frequencies: state.limits.eq.frequencies,
        range: state.limits.eq,
        labelFrequency,
        labelValue: labelGain,
        onInput(nextBands) {
          bands = nextBands;
          scheduleUpdate();
        },
      },
    });
  }
  balanceControl = controls.mount({
    ...regions[BALANCE_COMPONENT],
    root: balanceRoot,
    context: {
      value: balance,
      range: state.limits.balance,
      labelValue: labelBalance,
      onInput(nextBalance) {
        balance = nextBalance;
        scheduleBalanceUpdate();
      },
    },
  });
  metersControl = controls.mount({
    ...regions[METERS_COMPONENT],
    root: metersRoot,
    context: { levelPercent, formatLevel },
  });
  if (!usesToneBank) {
    spectrumRoot.hidden = false;
    spectrumControl = controls.mount({
      ...regions[SPECTRUM_COMPONENT],
      root: spectrumRoot,
      context: {
        bandCount: state.limits.eq.frequencies.length,
        eqRoot: equalizer,
        levelElements: eqControl.parts.levels,
        levelPercent,
      },
    });
  }
  metadataControl = controls.mount({
    ...regions[METADATA_COMPONENT],
    root: metadataRoot,
  });
  metadataControl.setValue({
    metadata: currentMetadata,
    transport: currentTransport,
  });
  presetsControl = controls.mount({
    ...regions[PRESETS_COMPONENT],
    root: presetsRoot,
    context: {
      run: runPresetAction,
      onSave: savePreset,
      onLoad: loadPreset,
      onExport: exportPreset,
      onDelete: deletePreset,
      onImport: importPreset,
    },
  });
  eqControl?.setValue(bands);
  toneBankControl?.setValue({ bands });
  balanceControl.setValue(balance);
  presetsControl.setValue({ presets: presetItems, selected: selectedPreset });
}

async function initialize() {
  try {
    const [state, descriptor] = await Promise.all([
      request("/api/v1/state"),
      initializeThemes(),
    ]);
    currentState = state;
    bands = state.tone.bands;
    balance = state.tone.balance;
    currentMetadata = state.metadata || {};
    currentTransport = state.transport || {};
    mountControls(state, descriptor);
    setEngineStatus({
      online: state.audio.engine === "running",
      error: state.audio.engine === "offline" ? "CamillaDSP is unavailable" : null,
    });
    activePreset = state.tone.preset;
    await refreshPresets(activePreset);
    connectEvents();
  } catch (error) {
    showMessage(error.message, true);
  }
}

matchMedia("(orientation: portrait)").addEventListener("change", () => {
  if (currentState && activeTheme) mountControls(currentState, activeTheme);
});

document.querySelector("#reset").addEventListener("click", () => {
  runPresetAction(async () => {
    await loadPreset("Flat");
    showMessage("Back to flat");
  });
});

initialize();
