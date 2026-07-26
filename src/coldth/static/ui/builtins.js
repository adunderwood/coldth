export const EQ_COMPONENT = "eq";
export const BALANCE_COMPONENT = "balance";
export const METERS_COMPONENT = "stereo-meters";
export const SPECTRUM_COMPONENT = "spectrum";
export const METADATA_COMPONENT = "metadata";
export const PRESETS_COMPONENT = "presets";
export const EQ_FADER_PRESENTATION =
  "coldth.presentation/vertical-fader@1";
export const BALANCE_SLIDER_PRESENTATION =
  "coldth.presentation/horizontal-slider@1";
export const LED_METERS_PRESENTATION = "coldth.presentation/led-bar@1";
export const SPECTRUM_OVERLAY_PRESENTATION =
  "coldth.presentation/ten-band-overlay@1";
export const NOW_PLAYING_PRESENTATION =
  "coldth.presentation/now-playing-display@1";
export const PRESET_SELECTOR_PRESENTATION =
  "coldth.presentation/preset-selector@1";

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

function mountNowPlaying({ root }) {
  root.dataset.component = METADATA_COMPONENT;
  root.dataset.presentation = NOW_PLAYING_PRESENTATION;
  root.className = "now-playing";
  root.hidden = true;
  root.replaceChildren();
  const artwork = document.createElement("img");
  artwork.alt = "";
  const detail = document.createElement("div");
  const state = document.createElement("span");
  const title = document.createElement("strong");
  const byline = document.createElement("small");
  detail.append(state, title, byline);
  root.append(artwork, detail);

  return {
    setValue(value = {}) {
      const metadata = value.metadata || {};
      const transport = value.transport || {};
      const available = Boolean(metadata.title || metadata.artist || metadata.album);
      root.hidden = !available;
      if (!available) return;
      title.textContent = metadata.title || "Unknown track";
      byline.textContent = [metadata.artist, metadata.album]
        .filter(Boolean)
        .join(" · ");
      state.textContent = transport.state === "playing" ? "Now playing" : "AirPlay";
      if (metadata.artwork) {
        artwork.src = `${metadata.artwork}?t=${Date.now()}`;
        artwork.hidden = false;
      } else {
        artwork.removeAttribute("src");
        artwork.hidden = true;
      }
    },
    dispose() {
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
    id: METADATA_COMPONENT,
    valueType: "metadata-state",
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
    id: NOW_PLAYING_PRESENTATION,
    valueTypes: ["metadata-state"],
    components: [METADATA_COMPONENT],
    optionsSchema: { properties: {} },
    mount: mountNowPlaying,
  });
  registry.registerPresentation({
    id: PRESET_SELECTOR_PRESENTATION,
    valueTypes: ["preset-collection"],
    components: [PRESETS_COMPONENT],
    optionsSchema: { properties: {} },
    mount: mountPresetSelector,
  });
}
