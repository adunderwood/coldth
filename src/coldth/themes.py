from __future__ import annotations

import io
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree

THEME_API_VERSION = 1
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_EXTRACTED_BYTES = 12 * 1024 * 1024
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_FILES = 128

THEME_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
REGION_ID = re.compile(r"^[a-z][a-z0-9-]*$")
SURFACE_IDS = {
    "meters",
    "balance",
    "spectrum",
    "track-info",
    "album-art",
    "tone",
    "presets",
}
HIDEABLE_SURFACE_IDS = {"meters", "spectrum", "track-info", "album-art"}

COMPONENT_PRESENTATIONS = {
    "eq": {"coldth.presentation/vertical-fader@1"},
    "balance": {"coldth.presentation/horizontal-slider@1"},
    "stereo-meters": {"coldth.presentation/led-bar@1"},
    "spectrum": {"coldth.presentation/ten-band-overlay@1"},
    "tone-bank": {"coldth.presentation/fader-ladder@1"},
    "track-info": {"coldth.presentation/now-playing-text@1"},
    "album-art": {"coldth.presentation/album-artwork@1"},
    "presets": {"coldth.presentation/preset-selector@1"},
}

PRESENTATION_OPTIONS: dict[str, dict[str, tuple[type, Any]]] = {
    "coldth.presentation/vertical-fader@1": {
        "orientation": (str, {"responsive", "vertical", "horizontal"})
    },
    "coldth.presentation/led-bar@1": {
        "releasePerFrame": (int | float, (0.1, 12.0))
    },
    "coldth.presentation/fader-ladder@1": {
        "orientation": (str, {"responsive", "vertical", "horizontal"}),
        "segments": (int, (8, 40)),
    },
}

ALLOWED_SUFFIXES = {
    ".css",
    ".json",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
    ".woff",
    ".woff2",
}


class ThemePackageError(ValueError):
    pass


class ThemeAlreadyInstalledError(ThemePackageError):
    pass


class ThemeDependencyError(ThemePackageError):
    pass


class ThemeVersionError(ThemePackageError):
    pass


def _version_key(version: str) -> tuple[int, int, int]:
    if not VERSION.fullmatch(version):
        raise ThemeVersionError(f"Invalid stored theme version: {version}")
    return tuple(int(part) for part in version.split("."))  # type: ignore[return-value]


def _require_text(value: Any, field: str, *, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ThemePackageError(f"{field} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise ThemePackageError(f"{field} is too long")
    return result


def _package_path(value: Any, field: str, *, suffixes: set[str]) -> str:
    text = _require_text(value, field, maximum=240)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or any(part in {"", "."} for part in path.parts)
    ):
        raise ThemePackageError(f"{field} must be a safe package-relative path")
    if path.suffix.lower() not in suffixes:
        raise ThemePackageError(f"{field} has an unsupported file type")
    return path.as_posix()


def _validate_tokens(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ThemePackageError("tokens must be an object")
    result: dict[str, str] = {}
    for name, token_value in value.items():
        if not isinstance(name, str) or not re.fullmatch(
            r"[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+", name
        ):
            raise ThemePackageError(f"Invalid semantic token name: {name}")
        result[name] = _require_text(token_value, f"tokens.{name}", maximum=160)
        if re.search(r"(?:url\s*\(|@import|[;{}])", result[name], re.IGNORECASE):
            raise ThemePackageError(f"Unsafe semantic token value: {name}")
    return result


def _validate_requires(value: Any) -> dict[str, list[str]]:
    if value is None:
        return {"components": [], "presentations": []}
    if not isinstance(value, dict) or set(value) - {"components", "presentations"}:
        raise ThemePackageError("requires must contain components and presentations")
    result: dict[str, list[str]] = {}
    for field in ("components", "presentations"):
        items = value.get(field, [])
        if not isinstance(items, list) or not all(
            isinstance(item, str) for item in items
        ):
            raise ThemePackageError(f"requires.{field} must be a text array")
        if len(items) != len(set(items)):
            raise ThemePackageError(f"requires.{field} contains duplicates")
        result[field] = items
    unknown_components = set(result["components"]) - set(COMPONENT_PRESENTATIONS)
    if unknown_components:
        raise ThemePackageError(
            f"Unknown required component: {sorted(unknown_components)[0]}"
        )
    known_presentations = set().union(*COMPONENT_PRESENTATIONS.values())
    unknown_presentations = set(result["presentations"]) - known_presentations
    if unknown_presentations:
        raise ThemePackageError(
            f"Unknown required presentation: {sorted(unknown_presentations)[0]}"
        )
    return result


def validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ThemePackageError("manifest.json must contain an object")
    allowed = {
        "id",
        "name",
        "description",
        "version",
        "apiVersion",
        "author",
        "extends",
        "styles",
        "preview",
        "layouts",
        "requires",
        "tokens",
    }
    unknown = set(value) - allowed
    if unknown:
        raise ThemePackageError(f"Unknown manifest field: {sorted(unknown)[0]}")

    theme_id = _require_text(value.get("id"), "id", maximum=120)
    if not THEME_ID.fullmatch(theme_id):
        raise ThemePackageError("id must be a lowercase reverse-domain identifier")
    if theme_id.startswith("coldth."):
        raise ThemePackageError("The coldth.* theme namespace is reserved")

    version = _require_text(value.get("version"), "version", maximum=40)
    if not VERSION.fullmatch(version):
        raise ThemePackageError("version must use major.minor.patch")
    api_version = value.get("apiVersion")
    if type(api_version) is not int or api_version != THEME_API_VERSION:
        raise ThemePackageError(
            f"apiVersion must be the supported value {THEME_API_VERSION}"
        )

    manifest: dict[str, Any] = {
        "id": theme_id,
        "name": _require_text(value.get("name"), "name"),
        "description": (
            _require_text(value["description"], "description", maximum=1000)
            if value.get("description")
            else ""
        ),
        "version": version,
        "apiVersion": api_version,
        "styles": _package_path(value.get("styles"), "styles", suffixes={".css"}),
        "requires": _validate_requires(value.get("requires")),
        "tokens": _validate_tokens(value.get("tokens")),
    }
    for field in ("author", "extends"):
        if value.get(field) is not None:
            manifest[field] = _require_text(value[field], field)
    if manifest.get("extends") == theme_id:
        raise ThemePackageError("A theme cannot extend itself")
    if value.get("preview") is not None:
        manifest["preview"] = _package_path(
            value["preview"],
            "preview",
            suffixes={".png", ".jpg", ".jpeg", ".webp"},
        )

    layouts = value.get("layouts", {})
    if not isinstance(layouts, dict) or set(layouts) - {"landscape", "portrait"}:
        raise ThemePackageError("layouts may contain landscape and portrait")
    manifest["layouts"] = {
        name: _package_path(path, f"layouts.{name}", suffixes={".json"})
        for name, path in layouts.items()
    }
    return manifest


def _validate_options(presentation: str, options: Any) -> dict[str, Any]:
    if options is None:
        return {}
    if not isinstance(options, dict):
        raise ThemePackageError("region options must be an object")
    rules = PRESENTATION_OPTIONS.get(presentation, {})
    unknown = set(options) - set(rules)
    if unknown:
        raise ThemePackageError(
            f"Unknown option for {presentation}: {sorted(unknown)[0]}"
        )
    for name, option in options.items():
        expected, constraint = rules[name]
        if isinstance(option, bool) or not isinstance(option, expected):
            raise ThemePackageError(f"Option {name} has the wrong type")
        if isinstance(constraint, set) and option not in constraint:
            raise ThemePackageError(f"Option {name} has an unsupported value")
        if isinstance(constraint, tuple) and not constraint[0] <= option <= constraint[1]:
            raise ThemePackageError(f"Option {name} is out of range")
    return options


def validate_layout(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or "regions" not in value
        or set(value) - {"regions", "flow", "hidden"}
    ):
        raise ThemePackageError(
            "layout must contain regions and optional flow and hidden"
        )
    regions = value["regions"]
    if not isinstance(regions, list) or not regions:
        raise ThemePackageError("layout regions must be a non-empty array")
    if len(regions) > 32:
        raise ThemePackageError("layout contains too many regions")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    for region in regions:
        if not isinstance(region, dict) or set(region) - {
            "id",
            "component",
            "presentation",
            "options",
        }:
            raise ThemePackageError("layout region has unknown fields")
        region_id = _require_text(region.get("id"), "region.id", maximum=80)
        if not REGION_ID.fullmatch(region_id) or region_id in ids:
            raise ThemePackageError(f"Invalid or duplicate region id: {region_id}")
        ids.add(region_id)
        component = _require_text(region.get("component"), "region.component")
        presentation = _require_text(
            region.get("presentation"), "region.presentation"
        )
        if component not in COMPONENT_PRESENTATIONS:
            raise ThemePackageError(f"Unknown component: {component}")
        if presentation not in COMPONENT_PRESENTATIONS[component]:
            raise ThemePackageError(
                f"{presentation} is incompatible with component {component}"
            )
        result.append(
            {
                "id": region_id,
                "component": component,
                "presentation": presentation,
                "options": _validate_options(presentation, region.get("options")),
            }
        )
    layout: dict[str, Any] = {"regions": result}
    if "flow" in value:
        flow = value["flow"]
        if (
            not isinstance(flow, list)
            or not flow
            or not all(isinstance(surface, str) for surface in flow)
            or len(flow) != len(set(flow))
        ):
            raise ThemePackageError("layout flow must be a non-empty unique array")
        unknown_surfaces = set(flow) - SURFACE_IDS
        if unknown_surfaces:
            raise ThemePackageError(
                f"Unknown layout surface: {sorted(unknown_surfaces)[0]}"
            )
        layout["flow"] = flow
    if "hidden" in value:
        hidden = value["hidden"]
        if (
            not isinstance(hidden, list)
            or not all(isinstance(surface, str) for surface in hidden)
            or len(hidden) != len(set(hidden))
        ):
            raise ThemePackageError("layout hidden must be a unique text array")
        unknown_hidden = set(hidden) - HIDEABLE_SURFACE_IDS
        if unknown_hidden:
            raise ThemePackageError(
                f"Layout surface cannot be hidden: {sorted(unknown_hidden)[0]}"
            )
        layout["hidden"] = hidden
    return layout


def _merge_layout(
    parent: dict[str, Any] | None, child: dict[str, Any]
) -> dict[str, Any]:
    if parent is None:
        result = {"regions": [dict(region) for region in child["regions"]]}
        if "flow" in child:
            result["flow"] = list(child["flow"])
        if "hidden" in child:
            result["hidden"] = list(child["hidden"])
        return result
    regions = [dict(region) for region in parent["regions"]]
    positions = {region["id"]: index for index, region in enumerate(regions)}
    for region in child["regions"]:
        replacement = dict(region)
        if replacement["id"] in positions:
            regions[positions[replacement["id"]]] = replacement
        else:
            positions[replacement["id"]] = len(regions)
            regions.append(replacement)
    result = {"regions": regions}
    flow = child.get("flow", parent.get("flow"))
    if flow is not None:
        result["flow"] = list(flow)
    hidden = child.get("hidden", parent.get("hidden"))
    if hidden is not None:
        result["hidden"] = list(hidden)
    return result


def _validate_css(payload: bytes, package_files: set[str]) -> None:
    try:
        css = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ThemePackageError("Theme CSS must be UTF-8") from error
    if "\\" in css:
        raise ThemePackageError("CSS escape sequences are not allowed")
    if re.search(r"@import\b", css, re.IGNORECASE):
        raise ThemePackageError("Remote or nested CSS imports are not allowed")
    for raw_url in re.findall(r"url\(\s*(['\"]?)(.*?)\1\s*\)", css, re.IGNORECASE):
        url = raw_url[1].strip()
        if (
            re.match(r"^(?:[a-z]+:|//|/)", url, re.IGNORECASE)
            or ".." in PurePosixPath(url.split("#", 1)[0]).parts
        ):
            raise ThemePackageError(f"Unsafe CSS URL: {url}")
        local_path = url.split("#", 1)[0].split("?", 1)[0]
        if local_path and local_path not in package_files:
            raise ThemePackageError(f"CSS references missing asset: {local_path}")


def _validate_svg(payload: bytes) -> None:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise ThemePackageError("Invalid SVG asset") from error
    forbidden_tags = {
        "script",
        "style",
        "foreignObject",
        "iframe",
        "object",
        "embed",
        "image",
        "a",
    }
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in forbidden_tags:
            raise ThemePackageError(f"Forbidden SVG element: {tag}")
        for name, value in element.attrib.items():
            attribute = name.rsplit("}", 1)[-1].lower()
            if attribute.startswith("on"):
                raise ThemePackageError("SVG event handlers are not allowed")
            clean_value = value.strip()
            if attribute in {"href", "src"} and clean_value and not clean_value.startswith(
                "#"
            ):
                raise ThemePackageError("External SVG references are not allowed")
            if re.search(r"(?:url\s*\(|@import)", clean_value, re.IGNORECASE):
                raise ThemePackageError("External SVG styles are not allowed")


class ThemeRegistry:
    def __init__(self, builtin_root: Path, installed_root: Path | None = None):
        self.builtin_root = builtin_root
        self.installed_root = installed_root
        if installed_root is not None:
            installed_root.mkdir(parents=True, exist_ok=True)

    def _builtin_themes(self) -> list[dict[str, Any]]:
        themes: list[dict[str, Any]] = []
        for manifest_path in sorted(self.builtin_root.glob("*/theme.json")):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            theme_id = manifest_path.parent.name
            if not isinstance(manifest, dict) or manifest.get("id") != theme_id:
                continue
            name = manifest.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            themes.append(
                {
                    "id": theme_id,
                    "name": name.strip(),
                    "description": str(manifest.get("description", "")).strip(),
                    "version": None,
                    "builtin": True,
                    "stylesheet": f"/assets/themes/{theme_id}/theme.css",
                }
            )
        return themes

    def _installed_package(
        self, theme_id: str
    ) -> tuple[Path, dict[str, Any]]:
        if self.installed_root is None:
            raise FileNotFoundError(theme_id)
        root = self.installed_root / theme_id
        try:
            manifest = validate_manifest(
                json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, ThemePackageError) as error:
            raise FileNotFoundError(theme_id) from error
        if manifest["id"] != theme_id:
            raise FileNotFoundError(theme_id)
        return root, manifest

    def _installed_summary(self, theme_id: str) -> dict[str, Any]:
        _, manifest = self._installed_package(theme_id)
        return {
            "id": theme_id,
            "name": manifest["name"],
            "description": manifest["description"],
            "version": manifest["version"],
            "builtin": False,
            "stylesheet": (
                f"/api/v1/themes/{theme_id}/assets/{manifest['styles']}"
                f"?v={manifest['version']}"
            ),
        }

    def _installed_themes(self) -> list[dict[str, Any]]:
        if self.installed_root is None:
            return []
        themes: list[dict[str, Any]] = []
        for root in sorted(self.installed_root.iterdir()):
            if not root.is_dir() or root.name.startswith("."):
                continue
            try:
                themes.append(self._installed_summary(root.name))
            except (FileNotFoundError, ThemePackageError):
                continue
        return themes

    def list(self) -> list[dict[str, Any]]:
        return sorted(
            self._builtin_themes() + self._installed_themes(),
            key=lambda theme: (theme["name"].casefold(), theme["id"]),
        )

    def _own_descriptor(self, theme_id: str) -> dict[str, Any]:
        summary = next((theme for theme in self.list() if theme["id"] == theme_id), None)
        if summary is None:
            raise FileNotFoundError(theme_id)

        if summary["builtin"]:
            manifest_path = self.builtin_root / theme_id / "theme.json"
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                layout_paths = manifest.get("layouts", {})
                if not isinstance(layout_paths, dict) or set(layout_paths) - {
                    "landscape",
                    "portrait",
                }:
                    raise ThemePackageError("Invalid built-in theme layouts")
                layouts = {
                    name: validate_layout(
                        json.loads(
                            (
                                manifest_path.parent
                                / _package_path(
                                    path,
                                    f"layouts.{name}",
                                    suffixes={".json"},
                                )
                            ).read_text(encoding="utf-8")
                        )
                    )
                    for name, path in layout_paths.items()
                }
            except (OSError, json.JSONDecodeError, ThemePackageError) as error:
                raise FileNotFoundError(theme_id) from error
            tokens = _validate_tokens(manifest.get("tokens"))
        else:
            try:
                root, manifest = self._installed_package(theme_id)
                layouts = {
                    name: validate_layout(
                        json.loads((root / path).read_text(encoding="utf-8"))
                    )
                    for name, path in manifest["layouts"].items()
                }
            except (OSError, json.JSONDecodeError, ThemePackageError) as error:
                raise FileNotFoundError(theme_id) from error
            tokens = manifest["tokens"]

        return {
            **summary,
            "apiVersion": THEME_API_VERSION,
            "extends": manifest.get("extends"),
            "tokens": tokens,
            "layouts": layouts,
            "stylesheets": [summary["stylesheet"]],
            "lineage": [theme_id],
        }

    def descriptor(
        self, theme_id: str, _ancestors: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        if theme_id in _ancestors:
            chain = " → ".join((*_ancestors, theme_id))
            raise ThemePackageError(f"Theme inheritance cycle: {chain}")
        descriptor = self._own_descriptor(theme_id)
        parent_id = descriptor.get("extends")
        if not parent_id:
            return descriptor
        try:
            parent = self.descriptor(parent_id, (*_ancestors, theme_id))
        except FileNotFoundError as error:
            raise ThemePackageError(
                f"Parent theme is not installed: {parent_id}"
            ) from error

        layouts = dict(parent["layouts"])
        for orientation, layout in descriptor["layouts"].items():
            layouts[orientation] = _merge_layout(layouts.get(orientation), layout)
        return {
            **descriptor,
            "tokens": {**parent["tokens"], **descriptor["tokens"]},
            "layouts": layouts,
            "stylesheets": [
                *parent["stylesheets"],
                *descriptor["stylesheets"],
            ],
            "lineage": [*parent["lineage"], theme_id],
        }

    def install_result(self, archive: bytes) -> dict[str, Any]:
        if self.installed_root is None:
            raise ThemePackageError("Theme installation is not configured")
        if not archive or len(archive) > MAX_ARCHIVE_BYTES:
            raise ThemePackageError("Theme archive is empty or too large")

        staging_parent = Path(
            tempfile.mkdtemp(prefix=".theme-", dir=self.installed_root)
        )
        extracted = staging_parent / "package"
        extracted.mkdir()
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as package:
                entries = package.infolist()
                files = [entry for entry in entries if not entry.is_dir()]
                if not files or len(files) > MAX_FILES:
                    raise ThemePackageError("Theme archive has an invalid file count")
                names: set[str] = set()
                total = 0
                for entry in entries:
                    name = entry.filename
                    path = PurePosixPath(name)
                    mode = entry.external_attr >> 16
                    if (
                        "\\" in name
                        or path.is_absolute()
                        or ".." in path.parts
                        or not path.parts
                        or any(part in {"", "."} for part in path.parts)
                    ):
                        raise ThemePackageError(f"Unsafe archive path: {name}")
                    if stat.S_ISLNK(mode):
                        raise ThemePackageError("Theme archives may not contain symlinks")
                    if not entry.is_dir():
                        if entry.flag_bits & 0x1:
                            raise ThemePackageError(
                                "Encrypted theme files are not supported"
                            )
                        if path.suffix.lower() not in ALLOWED_SUFFIXES:
                            raise ThemePackageError(
                                f"Unsupported package file: {name}"
                            )
                        if name in names:
                            raise ThemePackageError(f"Duplicate package file: {name}")
                        names.add(name)
                        if entry.file_size > MAX_FILE_BYTES:
                            raise ThemePackageError(f"Package file is too large: {name}")
                        total += entry.file_size
                        if total > MAX_EXTRACTED_BYTES:
                            raise ThemePackageError("Extracted theme is too large")

                if "manifest.json" not in names:
                    raise ThemePackageError("Theme archive is missing manifest.json")
                try:
                    manifest = validate_manifest(
                        json.loads(package.read("manifest.json").decode("utf-8"))
                    )
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ThemePackageError("manifest.json is invalid") from error

                referenced = {manifest["styles"], *manifest["layouts"].values()}
                if manifest.get("preview"):
                    referenced.add(manifest["preview"])
                missing = referenced - names
                if missing:
                    raise ThemePackageError(
                        f"Manifest references missing file: {sorted(missing)[0]}"
                    )
                if manifest.get("extends"):
                    try:
                        self.descriptor(manifest["extends"])
                    except FileNotFoundError as error:
                        raise ThemePackageError(
                            f"Parent theme is not installed: {manifest['extends']}"
                        ) from error
                for name in names:
                    if PurePosixPath(name).suffix.lower() == ".css":
                        _validate_css(package.read(name), names)
                for layout_path in manifest["layouts"].values():
                    try:
                        validate_layout(
                            json.loads(package.read(layout_path).decode("utf-8"))
                        )
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        raise ThemePackageError(
                            f"Invalid layout JSON: {layout_path}"
                        ) from error
                for name in names:
                    if PurePosixPath(name).suffix.lower() == ".svg":
                        _validate_svg(package.read(name))

                for entry in entries:
                    target = extracted.joinpath(*PurePosixPath(entry.filename).parts)
                    if entry.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with package.open(entry) as source, target.open("wb") as output:
                            shutil.copyfileobj(source, output)

            target = self.installed_root / manifest["id"]
            version = manifest["version"]
            previous_version: str | None = None
            operation = "installed"
            if target.exists():
                _, installed_manifest = self._installed_package(manifest["id"])
                previous_version = installed_manifest["version"]
                if version == previous_version:
                    raise ThemeAlreadyInstalledError(
                        f"Theme version is already installed: {manifest['id']} {version}"
                    )
                if _version_key(version) <= _version_key(previous_version):
                    raise ThemeVersionError(
                        f"Theme update must be newer than {previous_version}"
                    )
                backup = staging_parent / "previous"
                os.replace(target, backup)
                try:
                    os.replace(extracted, target)
                except Exception:
                    os.replace(backup, target)
                    raise
                operation = "updated"
            else:
                os.replace(extracted, target)
            return {
                "operation": operation,
                "previousVersion": previous_version,
                "theme": self._installed_summary(manifest["id"]),
            }
        except zipfile.BadZipFile as error:
            raise ThemePackageError("Theme package is not a valid ZIP archive") from error
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)

    def install(self, archive: bytes) -> dict[str, Any]:
        return self.install_result(archive)["theme"]

    def _dependents(self, theme_id: str) -> list[str]:
        dependents: set[str] = set()
        for manifest_path in self.builtin_root.glob("*/theme.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(manifest, dict) and manifest.get("extends") == theme_id:
                dependents.add(str(manifest.get("id", manifest_path.parent.name)))
        for summary in self._installed_themes():
            if summary["id"] == theme_id:
                continue
            try:
                _, manifest = self._installed_package(summary["id"])
            except FileNotFoundError:
                continue
            if manifest.get("extends") == theme_id:
                dependents.add(summary["id"])
        return sorted(dependents)

    def uninstall(self, theme_id: str) -> dict[str, Any]:
        if self.installed_root is None:
            raise FileNotFoundError(theme_id)
        summary = self._installed_summary(theme_id)
        dependents = self._dependents(theme_id)
        if dependents:
            raise ThemeDependencyError(
                f"Theme is required by: {', '.join(dependents)}"
            )
        root = self.installed_root / theme_id
        trash = self.installed_root / f".uninstall-{theme_id}"
        if trash.exists():
            shutil.rmtree(trash)
        os.replace(root, trash)
        shutil.rmtree(trash)
        return summary

    def asset(self, theme_id: str, asset_path: str) -> Path:
        if self.installed_root is None or not THEME_ID.fullmatch(theme_id):
            raise FileNotFoundError(theme_id)
        relative = PurePosixPath(asset_path)
        if (
            "\\" in asset_path
            or relative.is_absolute()
            or ".." in relative.parts
            or not relative.parts
            or any(part in {"", "."} for part in relative.parts)
        ):
            raise FileNotFoundError(asset_path)
        root = self._installed_package(theme_id)[0].resolve()
        candidate = root.joinpath(*relative.parts).resolve()
        if root not in candidate.parents or not candidate.is_file():
            raise FileNotFoundError(asset_path)
        if candidate.suffix.lower() not in ALLOWED_SUFFIXES:
            raise FileNotFoundError(asset_path)
        return candidate
