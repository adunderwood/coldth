export const EQ_COMPONENT = "eq";
export const BALANCE_COMPONENT = "balance";
export const METERS_COMPONENT = "stereo-meters";
export const SPECTRUM_COMPONENT = "spectrum";
export const TONE_BANK_COMPONENT = "tone-bank";
export const TRACK_INFO_COMPONENT = "track-info";
export const ALBUM_ART_COMPONENT = "album-art";
export const PRESETS_COMPONENT = "presets";
export const EQ_FADER_PRESENTATION =
  "coldth.presentation/vertical-fader@1";
export const BALANCE_SLIDER_PRESENTATION =
  "coldth.presentation/horizontal-slider@1";
export const LED_METERS_PRESENTATION = "coldth.presentation/led-bar@1";
export const SPECTRUM_OVERLAY_PRESENTATION =
  "coldth.presentation/ten-band-overlay@1";
export const FADER_LADDER_PRESENTATION =
  "coldth.presentation/fader-ladder@1";
export const NOW_PLAYING_TEXT_PRESENTATION =
  "coldth.presentation/now-playing-text@1";
export const ALBUM_ARTWORK_PRESENTATION =
  "coldth.presentation/album-artwork@1";
export const PRESET_SELECTOR_PRESENTATION =
  "coldth.presentation/preset-selector@1";

export function nowPlayingTextState(value = {}) {
  const metadata = value.metadata || {};
  const transport = value.transport || {};
  const hasMetadata = Boolean(
    metadata.title || metadata.artist || metadata.album,
  );
  const available = hasMetadata || transport.state === "playing";
  return {
    available,
    state: transport.state === "playing" ? "Now playing" : "AirPlay",
    title: hasMetadata
      ? metadata.title || "Unknown track"
      : "Waiting for track information",
    byline: hasMetadata
      ? [metadata.artist, metadata.album].filter(Boolean).join(" · ")
      : "Audio is playing",
  };
}

function mountEqFaders({ root, options, context }) {
  const listeners = [];
  const sliders = new Map();
  const outputs = new Map();
  let value = { ...context.value };

  root.dataset.component = EQ_COMPONENT;
  root.dataset.presentation = EQ_FADER_PRESENTATION;
  root.dataset.orientation = options.orientation;
  root.replaceChildren();

  for (const frequency of context.frequencies) {
    const key = String(frequency);
    const band = document.createElement("div");
    band.className = "band";
    const output = document.createElement("output");
    output.value = context.labelValue(value[key]);
    const wrap = document.createElement("div");
    wrap.className = "slider-wrap";
    const level = document.createElement("span");
    level.className = "band-level";
    level.setAttribute("aria-hidden", "true");
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = context.range.min;
    slider.max = context.range.max;
    slider.step = context.range.step;
    slider.value = value[key];
    slider.setAttribute("aria-label", `${frequency} hertz`);
    const onInput = () => {
      value = { ...value, [key]: Number(slider.value) };
      output.value = context.labelValue(value[key]);
      context.onInput({ ...value });
    };
    slider.addEventListener("input", onInput);
    listeners.push(() => slider.removeEventListener("input", onInput));
    const label = document.createElement("label");
    label.textContent = context.labelFrequency(frequency);
    wrap.append(level, slider);
    band.append(output, wrap, label);
    root.append(band);
    sliders.set(key, slider);
    outputs.set(key, output);
  }
  root.setAttribute("aria-busy", "false");

  return {
    setValue(nextValue) {
      value = { ...nextValue };
      for (const [key, slider] of sliders) {
        slider.value = value[key];
        outputs.get(key).value = context.labelValue(value[key]);
      }
    },
    dispose() {
      listeners.forEach((remove) => remove());
      root.replaceChildren();
    },
    parts: {
      levels() {
        return [...root.querySelectorAll(".band-level")];
      },
    },
  };
}

function mountBalanceSlider({ root, context }) {
  root.dataset.component = BALANCE_COMPONENT;
  root.dataset.presentation = BALANCE_SLIDER_PRESENTATION;
  root.replaceChildren();

  const left = document.createElement("span");
  left.textContent = "L";
  const right = document.createElement("span");
  right.textContent = "R";
  const label = document.createElement("label");
  const legend = document.createElement("span");
  legend.textContent = "Balance";
  const slider = document.createElement("input");
  slider.id = "balance";
  slider.type = "range";
  slider.min = context.range.min;
  slider.max = context.range.max;
  slider.step = context.range.step;
  const output = document.createElement("output");
  output.id = "balance-value";

  let value = context.value;
  const render = () => {
    slider.value = value;
    output.value = context.labelValue(value);
  };
  const onInput = () => {
    value = Number(slider.value);
    render();
    context.onInput(value);
  };
  const onDoubleClick = () => {
    value = 0;
    render();
    context.onInput(value);
  };
  slider.addEventListener("input", onInput);
  slider.addEventListener("dblclick", onDoubleClick);
  label.append(legend, slider);
  root.append(left, label, right, output);
  render();

  return {
    setValue(nextValue) {
      value = nextValue;
      render();
    },
    dispose() {
      slider.removeEventListener("input", onInput);
      slider.removeEventListener("dblclick", onDoubleClick);
      root.replaceChildren();
    },
  };
}

function mountLedMeters({ root, options, context }) {
  root.dataset.component = METERS_COMPONENT;
  root.dataset.presentation = LED_METERS_PRESENTATION;
  root.replaceChildren();
  const heldPeaks = [-60, -60];
  const rows = [0, 1].map((channel) => {
    const row = document.createElement("div");
    row.className = "meter-row";
    row.dataset.channel = channel;
    const label = document.createElement("span");
    label.className = "channel-label";
    label.textContent = channel === 0 ? "L" : "R";
    const track = document.createElement("div");
    track.className = "meter-track";
    const fill = document.createElement("span");
    fill.className = "meter-fill";
    const peak = document.createElement("i");
    peak.className = "peak-marker";
    track.append(fill, peak);
    const output = document.createElement("output");
    output.value = "−∞";
    row.append(label, track, output);
    root.append(row);
    return { fill, peak, output };
  });

  return {
    setValue(frame) {
      rows.forEach((row, channel) => {
        const rmsValue = Number(
          (channel === 0 ? frame?.leftRms : frame?.rightRms) ?? -60,
        );
        const peakValue = Number(
          (channel === 0 ? frame?.leftPeak : frame?.rightPeak) ?? rmsValue,
        );
        heldPeaks[channel] = Math.max(
          peakValue,
          heldPeaks[channel] - options.releasePerFrame,
        );
        row.fill.style.width = `${context.levelPercent(rmsValue)}%`;
        row.peak.style.left = `${context.levelPercent(heldPeaks[channel])}%`;
        row.output.value = context.formatLevel(peakValue);
      });
    },
    dispose() {
      root.replaceChildren();
    },
  };
}

function mountSpectrumOverlay({ root, context }) {
  root.dataset.component = SPECTRUM_COMPONENT;
  root.dataset.presentation = SPECTRUM_OVERLAY_PRESENTATION;
  const status = document.createElement("div");
  status.className = "analyzer-status";
  root.append(status);

  const render = (levels) => {
    const live = Array.isArray(levels) && levels.length === context.bandCount;
    context.eqRoot.classList.toggle("analyzer-live", live);
    status.classList.toggle("online", live);
    status.textContent = live
      ? `${context.bandCount}-band analyzer live`
      : `${context.bandCount}-band analyzer standby`;
    context.levelElements().forEach((level, index) => {
      level.style.setProperty(
        "--level",
        `${live ? context.levelPercent(levels[index]) : 0}%`,
      );
    });
  };
  render(null);

  return {
    setValue: render,
    dispose() {
      context.eqRoot.classList.remove("analyzer-live");
      context.levelElements().forEach((level) => {
        level.style.removeProperty("--level");
      });
      status.remove();
    },
  };
}

function mountFaderLadder({ root, options, context }) {
  const listeners = [];
  const strips = new Map();
  let bands = { ...context.value };
  let spectrum = null;

  root.dataset.component = TONE_BANK_COMPONENT;
  root.dataset.presentation = FADER_LADDER_PRESENTATION;
  root.dataset.orientation = options.orientation;
  root.replaceChildren();

  for (const frequency of context.frequencies) {
    const key = String(frequency);
    const strip = document.createElement("div");
    strip.className = "tone-strip";
    const output = document.createElement("output");
    output.value = context.labelValue(bands[key]);
    const control = document.createElement("div");
    control.className = "tone-strip-control";
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = context.range.min;
    slider.max = context.range.max;
    slider.step = context.range.step;
    slider.value = bands[key];
    slider.setAttribute("aria-label", `${frequency} hertz`);
    const fader = document.createElement("div");
    fader.className = "tone-fader";
    fader.append(slider);
    const ladder = document.createElement("div");
    ladder.className = "level-ladder";
    ladder.setAttribute("aria-hidden", "true");
    const segments = Array.from({ length: options.segments }, (_, index) => {
      const segment = document.createElement("i");
      segment.style.setProperty(
        "--segment-position",
        `${index / Math.max(1, options.segments - 1)}`,
      );
      const position = index / options.segments;
      segment.dataset.zone =
        position >= 0.8 ? "hot" : position >= 0.55 ? "warm" : "normal";
      ladder.append(segment);
      return segment;
    });
    const label = document.createElement("label");
    label.textContent = context.labelFrequency(frequency);
    const onInput = () => {
      bands = { ...bands, [key]: Number(slider.value) };
      output.value = context.labelValue(bands[key]);
      context.onInput({ ...bands });
    };
    slider.addEventListener("input", onInput);
    listeners.push(() => slider.removeEventListener("input", onInput));
    control.append(fader, ladder);
    strip.append(output, control, label);
    root.append(strip);
    strips.set(key, { slider, output, ladder, segments });
  }
  root.setAttribute("aria-busy", "false");

  const renderSpectrum = () => {
    const live =
      Array.isArray(spectrum) && spectrum.length === context.frequencies.length;
    root.classList.toggle("analyzer-live", live);
    context.frequencies.forEach((frequency, index) => {
      const { ladder, segments } = strips.get(String(frequency));
      const level = live ? context.levelPercent(spectrum[index]) / 100 : 0;
      const lit = Math.round(level * segments.length);
      ladder.dataset.activeSegments = String(lit);
      segments.forEach((segment, segmentIndex) => {
        segment.classList.toggle("active", segmentIndex < lit);
      });
    });
  };
  renderSpectrum();

  return {
    setValue(nextValue = {}) {
      if (nextValue.bands) {
        bands = { ...nextValue.bands };
        for (const [key, strip] of strips) {
          strip.slider.value = bands[key];
          strip.output.value = context.labelValue(bands[key]);
        }
      }
      if ("spectrum" in nextValue) {
        spectrum = nextValue.spectrum;
        renderSpectrum();
      }
    },
    dispose() {
      listeners.forEach((remove) => remove());
      root.replaceChildren();
      root.classList.remove("analyzer-live");
    },
  };
}

function mountNowPlayingText({ root, context }) {
  root.dataset.component = TRACK_INFO_COMPONENT;
  root.dataset.presentation = NOW_PLAYING_TEXT_PRESENTATION;
  root.className = "track-info";
  root.replaceChildren();
  const state = document.createElement("span");
  const title = document.createElement("strong");
  const byline = document.createElement("small");
  root.append(state, title, byline);

  return {
    setValue(value = {}) {
      const display = nowPlayingTextState(value);
      context.onAvailability(display.available);
      if (!display.available) return;
      title.textContent = display.title;
      byline.textContent = display.byline;
      state.textContent = display.state;
    },
    dispose() {
      context.onAvailability(false);
      root.replaceChildren();
    },
  };
}

function mountAlbumArtwork({ root, context }) {
  root.dataset.component = ALBUM_ART_COMPONENT;
  root.dataset.presentation = ALBUM_ARTWORK_PRESENTATION;
  root.className = "album-art";
  root.replaceChildren();
  const artwork = document.createElement("img");
  artwork.alt = "";
  root.append(artwork);
  let fingerprint = "";

  return {
    setValue(value = {}) {
      const metadata = value.metadata || {};
      const available = Boolean(metadata.artwork);
      context.onAvailability(available);
      if (!available) {
        artwork.removeAttribute("src");
        fingerprint = "";
        return;
      }
      const nextFingerprint = [
        metadata.artwork,
        metadata.artist,
        metadata.album,
        metadata.title,
      ].join("\n");
      if (nextFingerprint !== fingerprint) {
        fingerprint = nextFingerprint;
        artwork.src = `${metadata.artwork}?t=${Date.now()}`;
      }
    },
    dispose() {
      context.onAvailability(false);
      root.replaceChildren();
    },
  };
}

function mountPresetSelector({ root, context }) {
  root.dataset.component = PRESETS_COMPONENT;
  root.dataset.presentation = PRESET_SELECTOR_PRESENTATION;
  root.replaceChildren();

  const heading = document.createElement("div");
  heading.className = "section-heading";
  const headingText = document.createElement("div");
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = "Your settings";
  const title = document.createElement("h2");
  title.id = "preset-title";
  title.textContent = "Presets";
  headingText.append(eyebrow, title);
  const save = document.createElement("button");
  save.className = "primary-button";
  save.type = "button";
  save.textContent = "Save current";
  heading.append(headingText, save);

  const controls = document.createElement("div");
  controls.className = "preset-controls";
  const list = document.createElement("select");
  list.setAttribute("aria-label", "Choose preset");
  const load = button("Load");
  const exportButton = button("Export");
  const remove = button("Delete", "danger-button");
  const importLabel = document.createElement("label");
  importLabel.className = "import-button";
  importLabel.textContent = "Import";
  const importInput = document.createElement("input");
  importInput.type = "file";
  importInput.accept = "application/json,.json";
  importLabel.append(importInput);
  controls.append(list, load, exportButton, remove, importLabel);

  const dialog = document.createElement("dialog");
  const form = document.createElement("form");
  form.method = "dialog";
  const dialogEyebrow = document.createElement("p");
  dialogEyebrow.className = "eyebrow";
  dialogEyebrow.textContent = "New preset";
  const dialogTitle = document.createElement("h2");
  dialogTitle.textContent = "Save this shape";
  const nameLabel = document.createElement("label");
  nameLabel.textContent = "Preset name";
  const nameInput = document.createElement("input");
  nameInput.maxLength = 80;
  nameInput.autocomplete = "off";
  nameInput.required = true;
  nameLabel.append(nameInput);
  const actions = document.createElement("div");
  actions.className = "dialog-actions";
  const cancel = button("Cancel", "quiet-button");
  const confirmButton = button("Save preset", "primary-button");
  actions.append(cancel, confirmButton);
  form.append(dialogEyebrow, dialogTitle, nameLabel, actions);
  dialog.append(form);
  root.append(heading, controls, dialog);

  let value = { presets: [], selected: null };
  const render = () => {
    list.replaceChildren(
      ...value.presets.map((preset) => {
        const option = document.createElement("option");
        option.value = preset.name;
        option.textContent = preset.name;
        return option;
      }),
    );
    if (value.selected && value.presets.some((item) => item.name === value.selected)) {
      list.value = value.selected;
    }
    remove.disabled = list.value === "Flat";
  };
  const onSave = () => {
    nameInput.value = "";
    dialog.showModal();
    nameInput.focus();
  };
  const onConfirm = async (event) => {
    event.preventDefault();
    if (!nameInput.reportValidity()) return;
    await context.run(async () => {
      await context.onSave(nameInput.value);
      dialog.close();
    });
  };
  const onCancel = () => dialog.close();
  const onLoad = () => context.run(() => context.onLoad(list.value));
  const onExport = () => context.run(() => context.onExport(list.value));
  const onDelete = () => {
    const name = list.value;
    if (name !== "Flat" && globalThis.confirm(`Delete “${name}”?`)) {
      context.run(() => context.onDelete(name));
    }
  };
  const onSelection = () => {
    remove.disabled = list.value === "Flat";
  };
  const onImport = async () => {
    const [file] = importInput.files;
    if (!file) return;
    await context.run(() => context.onImport(file));
    importInput.value = "";
  };
  save.addEventListener("click", onSave);
  cancel.addEventListener("click", onCancel);
  confirmButton.addEventListener("click", onConfirm);
  load.addEventListener("click", onLoad);
  exportButton.addEventListener("click", onExport);
  remove.addEventListener("click", onDelete);
  list.addEventListener("change", onSelection);
  importInput.addEventListener("change", onImport);

  return {
    setValue(nextValue) {
      const hasSelection = Object.prototype.hasOwnProperty.call(
        nextValue,
        "selected",
      );
      value = {
        presets: [...(nextValue.presets || [])],
        selected: hasSelection ? nextValue.selected : list.value || null,
      };
      render();
    },
    dispose() {
      save.removeEventListener("click", onSave);
      cancel.removeEventListener("click", onCancel);
      confirmButton.removeEventListener("click", onConfirm);
      load.removeEventListener("click", onLoad);
      exportButton.removeEventListener("click", onExport);
      remove.removeEventListener("click", onDelete);
      list.removeEventListener("change", onSelection);
      importInput.removeEventListener("change", onImport);
      root.replaceChildren();
    },
  };
}

function button(label, className = "") {
  const element = document.createElement("button");
  element.type = "button";
  element.textContent = label;
  element.className = className;
  return element;
}

export function registerBuiltins(registry) {
  registry.registerComponent({
    id: EQ_COMPONENT,
    valueType: "band-collection",
    capability: "eq",
  });
  registry.registerComponent({
    id: METERS_COMPONENT,
    valueType: "stereo-level-frame",
    capability: "stereoMeters",
  });
  registry.registerComponent({
    id: SPECTRUM_COMPONENT,
    valueType: "band-measurements",
    capability: "spectrum",
  });
  registry.registerComponent({
    id: TONE_BANK_COMPONENT,
    valueType: "tone-bank-state",
    capability: "eq+spectrum",
  });
  registry.registerComponent({
    id: TRACK_INFO_COMPONENT,
    valueType: "metadata-state",
    capability: "metadata",
  });
  registry.registerComponent({
    id: ALBUM_ART_COMPONENT,
    valueType: "artwork-state",
    capability: "metadata",
  });
  registry.registerComponent({
    id: PRESETS_COMPONENT,
    valueType: "preset-collection",
    capability: "presets",
  });
  registry.registerComponent({
    id: BALANCE_COMPONENT,
    valueType: "continuous-bipolar",
    capability: "balance",
  });
  registry.registerPresentation({
    id: EQ_FADER_PRESENTATION,
    valueTypes: ["band-collection"],
    components: [EQ_COMPONENT],
    optionsSchema: {
      properties: {
        orientation: {
          type: "string",
          enum: ["responsive", "vertical", "horizontal"],
          default: "responsive",
        },
      },
    },
    mount: mountEqFaders,
  });
  registry.registerPresentation({
    id: BALANCE_SLIDER_PRESENTATION,
    valueTypes: ["continuous-bipolar"],
    components: [BALANCE_COMPONENT],
    optionsSchema: { properties: {} },
    mount: mountBalanceSlider,
  });
  registry.registerPresentation({
    id: LED_METERS_PRESENTATION,
    valueTypes: ["stereo-level-frame"],
    components: [METERS_COMPONENT],
    optionsSchema: {
      properties: {
        releasePerFrame: {
          type: "number",
          minimum: 0.1,
          maximum: 12,
          default: 0.7,
        },
      },
    },
    mount: mountLedMeters,
  });
  registry.registerPresentation({
    id: SPECTRUM_OVERLAY_PRESENTATION,
    valueTypes: ["band-measurements"],
    components: [SPECTRUM_COMPONENT],
    optionsSchema: { properties: {} },
    mount: mountSpectrumOverlay,
  });
  registry.registerPresentation({
    id: FADER_LADDER_PRESENTATION,
    valueTypes: ["tone-bank-state"],
    components: [TONE_BANK_COMPONENT],
    optionsSchema: {
      properties: {
        orientation: {
          type: "string",
          enum: ["responsive", "vertical", "horizontal"],
          default: "responsive",
        },
        segments: {
          type: "number",
          minimum: 8,
          maximum: 40,
          default: 24,
        },
      },
    },
    mount: mountFaderLadder,
  });
  registry.registerPresentation({
    id: NOW_PLAYING_TEXT_PRESENTATION,
    valueTypes: ["metadata-state"],
    components: [TRACK_INFO_COMPONENT],
    optionsSchema: { properties: {} },
    mount: mountNowPlayingText,
  });
  registry.registerPresentation({
    id: ALBUM_ARTWORK_PRESENTATION,
    valueTypes: ["artwork-state"],
    components: [ALBUM_ART_COMPONENT],
    optionsSchema: { properties: {} },
    mount: mountAlbumArtwork,
  });
  registry.registerPresentation({
    id: PRESET_SELECTOR_PRESENTATION,
    valueTypes: ["preset-collection"],
    components: [PRESETS_COMPONENT],
    optionsSchema: { properties: {} },
    mount: mountPresetSelector,
  });
}
