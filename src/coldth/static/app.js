import { ControlRegistry } from "./ui/registry.js";
import {
  BALANCE_COMPONENT,
  BALANCE_SLIDER_PRESENTATION,
  EQ_COMPONENT,
  EQ_FADER_PRESENTATION,
  LED_METERS_PRESENTATION,
  METADATA_COMPONENT,
  METERS_COMPONENT,
  NOW_PLAYING_PRESENTATION,
  PRESETS_COMPONENT,
  PRESET_SELECTOR_PRESENTATION,
  SPECTRUM_COMPONENT,
  SPECTRUM_OVERLAY_PRESENTATION,
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
const controls = new ControlRegistry();
registerBuiltins(controls);

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
  applyTheme();
}

function applyTheme() {
  const option = themeList.selectedOptions[0];
  if (!option) return;
  themeStylesheet.href = option.dataset.stylesheet;
  document.documentElement.dataset.theme = option.value;
  localStorage.setItem("coldth-theme", option.value);
}

themeList.addEventListener("change", applyTheme);

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
    reconnectTimer = setTimeout(connectEvents, 2000);
  });
  eventSocket.addEventListener("error", () => eventSocket.close());
}

function applyTone(tone = {}) {
  if (tone.bands) {
    bands = tone.bands;
    eqControl?.setValue(bands);
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

async function initialize() {
  try {
    const [state] = await Promise.all([
      request("/api/v1/state"),
      initializeThemes(),
    ]);
    bands = state.tone.bands;
    balance = state.tone.balance;
    eqControl = controls.mount({
      component: EQ_COMPONENT,
      presentation: EQ_FADER_PRESENTATION,
      root: equalizer,
      options: { orientation: "responsive" },
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
    balanceControl = controls.mount({
      component: BALANCE_COMPONENT,
      presentation: BALANCE_SLIDER_PRESENTATION,
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
      component: METERS_COMPONENT,
      presentation: LED_METERS_PRESENTATION,
      root: metersRoot,
      options: { releasePerFrame: 0.7 },
      context: { levelPercent, formatLevel },
    });
    spectrumControl = controls.mount({
      component: SPECTRUM_COMPONENT,
      presentation: SPECTRUM_OVERLAY_PRESENTATION,
      root: spectrumRoot,
      context: {
        bandCount: state.limits.eq.frequencies.length,
        eqRoot: equalizer,
        levelElements: eqControl.parts.levels,
        levelPercent,
      },
    });
    currentMetadata = state.metadata || {};
    currentTransport = state.transport || {};
    metadataControl = controls.mount({
      component: METADATA_COMPONENT,
      presentation: NOW_PLAYING_PRESENTATION,
      root: metadataRoot,
    });
    metadataControl.setValue({
      metadata: currentMetadata,
      transport: currentTransport,
    });
    presetsControl = controls.mount({
      component: PRESETS_COMPONENT,
      presentation: PRESET_SELECTOR_PRESENTATION,
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

document.querySelector("#reset").addEventListener("click", () => {
  runPresetAction(async () => {
    await loadPreset("Flat");
    showMessage("Back to flat");
  });
});

initialize();
