const metadataEnabled = document.querySelector("#metadata-enabled");
const artworkEnabled = document.querySelector("#artwork-enabled");
const metadataSource = document.querySelector("#metadata-source");
const settingsMessage = document.querySelector("#settings-message");
const themeStylesheet = document.querySelector("#theme-stylesheet");
const themePackage = document.querySelector("#theme-package");
const installedThemes = document.querySelector("#installed-themes");

let selectedTheme = localStorage.getItem("coldth-theme") || "original-yellow";
document.documentElement.dataset.theme = selectedTheme;
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

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

function renderThemes(themes) {
  installedThemes.replaceChildren(
    ...themes.map((theme) => {
      const row = document.createElement("div");
      row.className = "installed-theme";
      const text = document.createElement("span");
      const name = document.createElement("strong");
      name.textContent = theme.name;
      const detail = document.createElement("small");
      detail.textContent = theme.builtin
        ? "Bundled with Coldth"
        : `${theme.id} · ${theme.version}`;
      text.append(name, detail);
      const actions = document.createElement("span");
      actions.className = "theme-actions";
      if (theme.id === selectedTheme) {
        const state = document.createElement("span");
        state.className = "source-status";
        state.textContent = "Selected";
        actions.append(state);
      } else {
        const select = document.createElement("button");
        select.type = "button";
        select.className = "quiet-button";
        select.textContent = "Use theme";
        select.addEventListener("click", () => selectTheme(theme));
        actions.append(select);
      }
      if (!theme.builtin) {
        const uninstall = document.createElement("button");
        uninstall.type = "button";
        uninstall.className = "danger-button";
        uninstall.textContent = "Uninstall";
        uninstall.addEventListener("click", () => uninstallTheme(theme));
        actions.append(uninstall);
      }
      row.append(text, actions);
      return row;
    }),
  );
}

async function refreshThemes() {
  const themes = await request("/api/v1/themes");
  renderThemes(themes);
  return themes;
}

function applyThemeDescriptor(descriptor) {
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
  for (const property of Object.values(TOKEN_PROPERTIES)) {
    document.documentElement.style.removeProperty(property);
  }
  for (const [token, value] of Object.entries(descriptor.tokens || {})) {
    const property = TOKEN_PROPERTIES[token];
    if (property) document.documentElement.style.setProperty(property, value);
  }
  selectedTheme = descriptor.id;
  document.documentElement.dataset.theme = selectedTheme;
  localStorage.setItem("coldth-theme", selectedTheme);
}

async function selectTheme(theme) {
  settingsMessage.textContent = `Applying “${theme.name}”…`;
  settingsMessage.classList.remove("error");
  try {
    const descriptor = await request(
      `/api/v1/themes/${encodeURIComponent(theme.id)}`,
    );
    applyThemeDescriptor(descriptor);
    await refreshThemes();
    settingsMessage.textContent = `Using “${theme.name}”`;
  } catch (error) {
    settingsMessage.textContent = error.message;
    settingsMessage.classList.add("error");
  }
}

async function uninstallTheme(theme) {
  if (!globalThis.confirm(`Uninstall “${theme.name}”?`)) {
    return;
  }
  settingsMessage.textContent = `Uninstalling “${theme.name}”…`;
  settingsMessage.classList.remove("error");
  try {
    await request(`/api/v1/themes/${encodeURIComponent(theme.id)}`, {
      method: "DELETE",
    });
    if (selectedTheme === theme.id) {
      const fallback = await request("/api/v1/themes/original-yellow");
      applyThemeDescriptor(fallback);
    }
    await refreshThemes();
    settingsMessage.textContent = `Uninstalled “${theme.name}”`;
  } catch (error) {
    settingsMessage.textContent = error.message;
    settingsMessage.classList.add("error");
  }
}

function applyPrivacy(privacy) {
  metadataEnabled.checked = privacy.metadata;
  artworkEnabled.checked = privacy.artwork;
  artworkEnabled.disabled = !privacy.metadata;
}

async function savePrivacy() {
  metadataEnabled.disabled = true;
  artworkEnabled.disabled = true;
  settingsMessage.textContent = "Saving…";
  settingsMessage.classList.remove("error");
  try {
    const result = await request("/api/v1/settings/privacy", {
      method: "PUT",
      body: JSON.stringify({
        metadata: metadataEnabled.checked,
        artwork: metadataEnabled.checked && artworkEnabled.checked,
      }),
    });
    applyPrivacy(result.privacy);
    settingsMessage.textContent = "Settings saved";
  } catch (error) {
    settingsMessage.textContent = error.message;
    settingsMessage.classList.add("error");
  } finally {
    metadataEnabled.disabled = false;
    artworkEnabled.disabled = !metadataEnabled.checked;
  }
}

metadataEnabled.addEventListener("change", () => {
  if (!metadataEnabled.checked) artworkEnabled.checked = false;
  savePrivacy();
});
artworkEnabled.addEventListener("change", savePrivacy);
themePackage.addEventListener("change", async () => {
  const [file] = themePackage.files;
  if (!file) return;
  themePackage.disabled = true;
  settingsMessage.textContent = "Validating theme…";
  settingsMessage.classList.remove("error");
  try {
    const result = await request("/api/v1/themes/install", {
      method: "POST",
      headers: { "Content-Type": "application/zip" },
      body: file,
    });
    await refreshThemes();
    settingsMessage.textContent =
      result.operation === "updated"
        ? `Updated “${result.theme.name}” to ${result.theme.version}`
        : `Installed “${result.theme.name}”`;
  } catch (error) {
    settingsMessage.textContent = error.message;
    settingsMessage.classList.add("error");
  } finally {
    themePackage.value = "";
    themePackage.disabled = false;
  }
});

Promise.all([
  request("/api/v1/settings"),
  refreshThemes(),
  request(`/api/v1/themes/${encodeURIComponent(selectedTheme)}`).catch(() =>
    request("/api/v1/themes/original-yellow"),
  ),
])
  .then(async ([settings, , descriptor]) => {
    applyThemeDescriptor(descriptor);
    await refreshThemes();
    applyPrivacy(settings.privacy);
    const configured = settings.sources.shairportMetadata.configured;
    metadataSource.textContent = configured
      ? "Shairport source ready"
      : "Shairport source not configured";
    metadataSource.classList.toggle("online", configured);
  })
  .catch((error) => {
    settingsMessage.textContent = error.message;
    settingsMessage.classList.add("error");
  });
