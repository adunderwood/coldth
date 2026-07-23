const equalizer = document.querySelector("#equalizer");
const engineStatus = document.querySelector("#engine-status");
const message = document.querySelector("#message");
const presetList = document.querySelector("#preset-list");
const saveDialog = document.querySelector("#save-dialog");
const presetName = document.querySelector("#preset-name");

let bands = {};
let updateTimer;

const labelFrequency = (frequency) =>
  frequency >= 1000 ? `${frequency / 1000}k` : `${frequency}`;

const labelGain = (gain) => `${gain > 0 ? "+" : ""}${gain.toFixed(1)} dB`;

function showMessage(text, error = false) {
  message.textContent = text;
  message.classList.toggle("error", error);
}

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

function renderBands(frequencies, range) {
  equalizer.replaceChildren();
  for (const frequency of frequencies) {
    const key = String(frequency);
    const band = document.createElement("div");
    band.className = "band";
    const output = document.createElement("output");
    output.value = labelGain(bands[key]);
    const wrap = document.createElement("div");
    wrap.className = "slider-wrap";
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = range.min;
    slider.max = range.max;
    slider.step = range.step;
    slider.value = bands[key];
    slider.setAttribute("aria-label", `${frequency} hertz`);
    slider.addEventListener("input", () => {
      bands[key] = Number(slider.value);
      output.value = labelGain(bands[key]);
      scheduleUpdate();
    });
    const label = document.createElement("label");
    label.textContent = labelFrequency(frequency);
    wrap.append(slider);
    band.append(output, wrap, label);
    equalizer.append(band);
  }
  equalizer.setAttribute("aria-busy", "false");
}

function updateSliders() {
  [...equalizer.querySelectorAll("input")].forEach((slider) => {
    const frequency = slider.getAttribute("aria-label").split(" ")[0];
    slider.value = bands[frequency];
    slider.closest(".band").querySelector("output").value = labelGain(
      bands[frequency],
    );
  });
}

function scheduleUpdate() {
  clearTimeout(updateTimer);
  updateTimer = setTimeout(async () => {
    try {
      const result = await request("/api/eq", {
        method: "PUT",
        body: JSON.stringify({ bands }),
      });
      setEngineStatus(result.engine);
      showMessage(result.applied ? "EQ applied" : "Saved; audio engine is offline");
    } catch (error) {
      showMessage(error.message, true);
    }
  }, 120);
}

async function refreshPresets(selected) {
  const presets = await request("/api/presets");
  presetList.replaceChildren(
    ...presets.map((preset) => {
      const option = document.createElement("option");
      option.value = preset.name;
      option.textContent = preset.name;
      return option;
    }),
  );
  if (selected) presetList.value = selected;
  document.querySelector("#delete-preset").disabled =
    presetList.value === "Flat";
}

async function initialize() {
  try {
    const state = await request("/api/state");
    bands = state.bands;
    renderBands(state.frequencies, state.range);
    setEngineStatus(state.engine);
    await refreshPresets();
  } catch (error) {
    showMessage(error.message, true);
  }
}

document.querySelector("#reset").addEventListener("click", async () => {
  try {
    const result = await request("/api/reset", { method: "POST" });
    bands = result.bands;
    updateSliders();
    setEngineStatus(result.engine);
    showMessage("Back to flat");
  } catch (error) {
    showMessage(error.message, true);
  }
});

document.querySelector("#save-preset").addEventListener("click", () => {
  presetName.value = "";
  saveDialog.showModal();
  presetName.focus();
});

document.querySelector("#confirm-save").addEventListener("click", async (event) => {
  event.preventDefault();
  if (!presetName.reportValidity()) return;
  try {
    const preset = await request("/api/presets", {
      method: "POST",
      body: JSON.stringify({ name: presetName.value, bands }),
    });
    saveDialog.close();
    await refreshPresets(preset.name);
    showMessage(`Saved “${preset.name}”`);
  } catch (error) {
    showMessage(error.message, true);
  }
});

document.querySelector("#load-preset").addEventListener("click", async () => {
  try {
    const result = await request(
      `/api/presets/${encodeURIComponent(presetList.value)}/load`,
      { method: "POST" },
    );
    bands = result.bands;
    updateSliders();
    setEngineStatus(result.engine);
    showMessage(`Loaded “${presetList.value}”`);
  } catch (error) {
    showMessage(error.message, true);
  }
});

document.querySelector("#delete-preset").addEventListener("click", async () => {
  const name = presetList.value;
  if (name === "Flat" || !confirm(`Delete “${name}”?`)) return;
  try {
    await request(`/api/presets/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
    await refreshPresets();
    showMessage(`Deleted “${name}”`);
  } catch (error) {
    showMessage(error.message, true);
  }
});

presetList.addEventListener("change", () => {
  document.querySelector("#delete-preset").disabled =
    presetList.value === "Flat";
});

document.querySelector("#export-preset").addEventListener("click", async () => {
  try {
    const preset = await request(
      `/api/presets/${encodeURIComponent(presetList.value)}/export`,
    );
    const blob = new Blob([`${JSON.stringify(preset, null, 2)}\n`], {
      type: "application/json",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${preset.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (error) {
    showMessage(error.message, true);
  }
});

document.querySelector("#import-preset").addEventListener("change", async (event) => {
  const [file] = event.target.files;
  if (!file) return;
  try {
    const preset = await request("/api/presets/import", {
      method: "POST",
      body: await file.text(),
    });
    await refreshPresets(preset.name);
    showMessage(`Imported “${preset.name}”`);
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    event.target.value = "";
  }
});

initialize();
