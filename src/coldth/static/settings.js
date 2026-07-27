const metadataEnabled = document.querySelector("#metadata-enabled");
const artworkEnabled = document.querySelector("#artwork-enabled");
const metadataSource = document.querySelector("#metadata-source");
const settingsMessage = document.querySelector("#settings-message");
const themeStylesheet = document.querySelector("#theme-stylesheet");
const themePackage = document.querySelector("#theme-package");
const installedThemes = document.querySelector("#installed-themes");

let selectedTheme = localStorage.getItem("coldth-theme") || "original-yellow";
document.documentElement.dataset.theme = selectedTheme;

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
  const selected = themes.find((theme) => theme.id === selectedTheme);
  themeStylesheet.href =
    selected?.stylesheet || "/assets/themes/original-yellow/theme.css";
}

async function refreshThemes() {
  const themes = await request("/api/v1/themes");
  renderThemes(themes);
  return themes;
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
      selectedTheme = "original-yellow";
      localStorage.setItem("coldth-theme", selectedTheme);
      document.documentElement.dataset.theme = selectedTheme;
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

Promise.all([request("/api/v1/settings"), refreshThemes()])
  .then(([settings]) => {
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
