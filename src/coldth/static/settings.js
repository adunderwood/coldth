const metadataEnabled = document.querySelector("#metadata-enabled");
const artworkEnabled = document.querySelector("#artwork-enabled");
const metadataSource = document.querySelector("#metadata-source");
const artworkDescription = document.querySelector("#artwork-description");
const settingsMessage = document.querySelector("#settings-message");
const themeStylesheet = document.querySelector("#theme-stylesheet");

const savedTheme = localStorage.getItem("coldth-theme") || "original-yellow";
themeStylesheet.href = `/assets/themes/${savedTheme}/theme.css`;
document.documentElement.dataset.theme = savedTheme;

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

let artworkAvailable = false;

function applyPrivacy(privacy) {
  metadataEnabled.checked = privacy.metadata;
  artworkEnabled.checked = privacy.artwork;
  artworkEnabled.disabled = !privacy.metadata || !artworkAvailable;
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
    artworkEnabled.disabled = !metadataEnabled.checked || !artworkAvailable;
  }
}

metadataEnabled.addEventListener("change", () => {
  if (!metadataEnabled.checked) artworkEnabled.checked = false;
  savePrivacy();
});
artworkEnabled.addEventListener("change", savePrivacy);

request("/api/v1/settings")
  .then((settings) => {
    applyPrivacy(settings.privacy);
    const configured = settings.sources.shairportMetadata.configured;
    artworkAvailable = settings.sources.shairportMetadata.artworkAvailable;
    applyPrivacy(settings.privacy);
    metadataSource.textContent = configured
      ? "Shairport source ready"
      : "Shairport source not configured";
    metadataSource.classList.toggle("online", configured);
    if (!artworkAvailable) {
      artworkDescription.textContent =
        "Artwork requests are disabled in Shairport. See the Pi installation guide to opt in.";
    }
  })
  .catch((error) => {
    settingsMessage.textContent = error.message;
    settingsMessage.classList.add("error");
  });
