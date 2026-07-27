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

import yaml

THEME_API_VERSION = 1
FACEPLATE_LANGUAGE = "coldth.faceplate"
FACEPLATE_SCHEMA_VERSION = "0.1"
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
SURFACE_PARTS = {
    "meters": {"channel", "channel-label", "track", "fill", "peak", "value"},
    "balance": {"left-label", "right-label", "legend", "control", "value"},
    "spectrum": {"status"},
    "track-info": {"state", "title", "byline"},
    "album-art": {"image"},
    "tone": {
        "band",
        "value",
        "track",
        "level",
        "control-group",
        "control",
        "ladder",
        "segment",
        "label",
    },
    "presets": {
        "heading",
        "save",
        "controls",
        "list",
        "load",
        "export",
        "delete",
        "import",
        "save-dialog",
    },
}

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
    ".yaml",
    ".yml",
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
        "faceplate",
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
    if value.get("faceplate") is not None:
        manifest["faceplate"] = _package_path(
            value["faceplate"],
            "faceplate",
            suffixes={".yaml", ".yml"},
        )

    layouts = value.get("layouts", {})
    if not isinstance(layouts, dict) or set(layouts) - {"landscape", "portrait"}:
        raise ThemePackageError("layouts may contain landscape and portrait")
    manifest["layouts"] = {
        name: _package_path(path, f"layouts.{name}", suffixes={".json"})
        for name, path in layouts.items()
    }
    if manifest.get("faceplate") and manifest["layouts"]:
        raise ThemePackageError("manifest must use faceplate or layouts, not both")
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
        or set(value) - {"regions", "groups", "flow", "hidden"}
    ):
        raise ThemePackageError(
            "layout must contain regions and optional groups, flow, and hidden"
        )
    regions = value["regions"]
    if not isinstance(regions, list):
        raise ThemePackageError("layout regions must be an array")
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
    groups = value.get("groups", [])
    if not isinstance(groups, list) or len(groups) > 16:
        raise ThemePackageError("layout groups must be an array of at most 16 groups")
    group_ids: set[str] = set()
    grouped_surfaces: set[str] = set()
    validated_groups: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict) or set(group) != {
            "id",
            "surfaces",
            "direction",
        }:
            raise ThemePackageError(
                "layout group must contain id, surfaces, and direction"
            )
        group_id = _require_text(group.get("id"), "group.id", maximum=80)
        if (
            not REGION_ID.fullmatch(group_id)
            or group_id in group_ids
            or group_id in SURFACE_IDS
        ):
            raise ThemePackageError(f"Invalid or duplicate group id: {group_id}")
        surfaces = group.get("surfaces")
        if (
            not isinstance(surfaces, list)
            or len(surfaces) < 2
            or not all(isinstance(surface, str) for surface in surfaces)
            or len(surfaces) != len(set(surfaces))
        ):
            raise ThemePackageError(
                f"Group {group_id} surfaces must be a unique array of at least two"
            )
        unknown_surfaces = set(surfaces) - SURFACE_IDS
        if unknown_surfaces:
            raise ThemePackageError(
                f"Unknown group surface: {sorted(unknown_surfaces)[0]}"
            )
        duplicate_surface = set(surfaces) & grouped_surfaces
        if duplicate_surface:
            raise ThemePackageError(
                f"Surface belongs to multiple groups: {sorted(duplicate_surface)[0]}"
            )
        direction = group.get("direction")
        if direction not in {"row", "column"}:
            raise ThemePackageError(
                f"Group {group_id} direction must be row or column"
            )
        group_ids.add(group_id)
        grouped_surfaces.update(surfaces)
        validated_groups.append(
            {"id": group_id, "surfaces": list(surfaces), "direction": direction}
        )
    if validated_groups:
        layout["groups"] = validated_groups
    if "flow" in value:
        flow = value["flow"]
        if (
            not isinstance(flow, list)
            or not flow
            or not all(isinstance(surface, str) for surface in flow)
            or len(flow) != len(set(flow))
        ):
            raise ThemePackageError("layout flow must be a non-empty unique array")
        unknown_items = set(flow) - SURFACE_IDS - group_ids
        if unknown_items:
            raise ThemePackageError(
                f"Unknown layout flow item: {sorted(unknown_items)[0]}"
            )
        grouped_in_flow = set(flow) & grouped_surfaces
        if grouped_in_flow:
            raise ThemePackageError(
                f"Grouped surface cannot appear directly in flow: "
                f"{sorted(grouped_in_flow)[0]}"
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


def _faceplate_number(
    value: Any,
    path: str,
    *,
    maximum: float,
) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ThemePackageError(f"{path} must be a number")
    if not 0 <= value <= maximum:
        raise ThemePackageError(f"{path} must be between 0 and {maximum:g}")
    return value


def _faceplate_size(value: Any, path: str) -> str | int | float:
    if isinstance(value, str) and value in {"fill", "hug"}:
        return value
    return _faceplate_number(value, path, maximum=4096)


def _faceplate_padding(value: Any, path: str) -> int | float | list[int | float]:
    if isinstance(value, list):
        if len(value) not in {2, 4}:
            raise ThemePackageError(f"{path} must contain two or four numbers")
        return [
            _faceplate_number(item, f"{path}[{index}]", maximum=256)
            for index, item in enumerate(value)
        ]
    return _faceplate_number(value, path, maximum=256)


def _validate_faceplate_node(
    value: Any,
    path: str,
    *,
    depth: int,
    frame_ids: set[str],
    surface_ids: set[str],
    seen: set[int],
    node_count: list[int],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ThemePackageError(f"{path} must be an object")
    if id(value) in seen:
        raise ThemePackageError(f"{path} contains a recursive YAML alias")
    seen.add(id(value))
    node_count[0] += 1
    if depth > 8 or node_count[0] > 64:
        raise ThemePackageError("faceplate frame tree is too large")

    node_types = {"frame", "surface"} & set(value)
    if len(node_types) != 1:
        raise ThemePackageError(f"{path} must declare exactly one frame or surface")
    node_type = next(iter(node_types))

    common_fields = {"width", "height"}
    if node_type == "surface":
        unknown = set(value) - {"surface", *common_fields}
        if unknown:
            raise ThemePackageError(
                f"Unknown field at {path}: {sorted(unknown)[0]}"
            )
        surface = _require_text(value["surface"], f"{path}.surface", maximum=80)
        if surface not in SURFACE_IDS:
            raise ThemePackageError(f"Unknown surface at {path}: {surface}")
        if surface in surface_ids:
            raise ThemePackageError(f"Duplicate surface at {path}: {surface}")
        surface_ids.add(surface)
        result: dict[str, Any] = {"type": "surface", "id": surface}
    else:
        allowed = {
            "frame",
            "direction",
            "gap",
            "padding",
            "align",
            "justify",
            "wrap",
            "children",
            *common_fields,
        }
        unknown = set(value) - allowed
        if unknown:
            raise ThemePackageError(
                f"Unknown field at {path}: {sorted(unknown)[0]}"
            )
        frame = _require_text(value["frame"], f"{path}.frame", maximum=80)
        if (
            not REGION_ID.fullmatch(frame)
            or frame in frame_ids
            or frame in SURFACE_IDS
        ):
            raise ThemePackageError(f"Invalid or duplicate frame at {path}: {frame}")
        frame_ids.add(frame)
        direction = value.get("direction", "column")
        if direction not in {"row", "column"}:
            raise ThemePackageError(f"{path}.direction must be row or column")
        align = value.get("align", "stretch")
        if align not in {"start", "center", "end", "stretch"}:
            raise ThemePackageError(
                f"{path}.align must be start, center, end, or stretch"
            )
        justify = value.get("justify", "start")
        if justify not in {"start", "center", "end", "space-between"}:
            raise ThemePackageError(
                f"{path}.justify has an unsupported value"
            )
        wrap = value.get("wrap", False)
        if type(wrap) is not bool:
            raise ThemePackageError(f"{path}.wrap must be true or false")
        children = value.get("children")
        if not isinstance(children, list) or not children:
            raise ThemePackageError(f"{path}.children must be a non-empty array")
        result = {
            "type": "frame",
            "id": frame,
            "direction": direction,
            "gap": _faceplate_number(value.get("gap", 0), f"{path}.gap", maximum=256),
            "padding": _faceplate_padding(
                value.get("padding", 0), f"{path}.padding"
            ),
            "align": align,
            "justify": justify,
            "wrap": wrap,
            "children": [
                _validate_faceplate_node(
                    child,
                    f"{path}.children[{index}]",
                    depth=depth + 1,
                    frame_ids=frame_ids,
                    surface_ids=surface_ids,
                    seen=seen,
                    node_count=node_count,
                )
                for index, child in enumerate(children)
            ],
        }

    for field in common_fields:
        if field in value:
            result[field] = _faceplate_size(value[field], f"{path}.{field}")
    return result


def validate_faceplate(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ThemePackageError("faceplate document must contain an object")
    unknown = set(value) - {"language", "schemaVersion", "layouts"}
    if unknown:
        raise ThemePackageError(
            f"Unknown faceplate document field: {sorted(unknown)[0]}"
        )
    if value.get("language") != FACEPLATE_LANGUAGE:
        raise ThemePackageError(f"language must be {FACEPLATE_LANGUAGE}")
    if value.get("schemaVersion") != FACEPLATE_SCHEMA_VERSION:
        raise ThemePackageError(
            f"schemaVersion must be the supported value "
            f"{FACEPLATE_SCHEMA_VERSION}"
        )
    layouts = value.get("layouts")
    if (
        not isinstance(layouts, dict)
        or not layouts
        or set(layouts) - {"landscape", "portrait"}
    ):
        raise ThemePackageError(
            "faceplate layouts must contain landscape or portrait"
        )

    normalized: dict[str, Any] = {}
    for orientation, layout_value in layouts.items():
        path = f"layouts.{orientation}"
        if not isinstance(layout_value, dict):
            raise ThemePackageError(f"{path} must be an object")
        unknown_layout = set(layout_value) - {"root", "regions", "hidden"}
        if unknown_layout:
            raise ThemePackageError(
                f"Unknown field at {path}: {sorted(unknown_layout)[0]}"
            )
        legacy_fields: dict[str, Any] = {
            "regions": layout_value.get("regions", [])
        }
        if "hidden" in layout_value:
            legacy_fields["hidden"] = layout_value["hidden"]
        validated = validate_layout(legacy_fields)
        validated["frame"] = _validate_faceplate_node(
            layout_value.get("root"),
            f"{path}.root",
            depth=0,
            frame_ids=set(),
            surface_ids=set(),
            seen=set(),
            node_count=[0],
        )
        if validated["frame"]["type"] != "frame":
            raise ThemePackageError(f"{path}.root must declare a frame")
        normalized[orientation] = validated

    return {
        "language": FACEPLATE_LANGUAGE,
        "schemaVersion": FACEPLATE_SCHEMA_VERSION,
        "layouts": normalized,
    }


def load_faceplate(payload: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(payload)
    except yaml.YAMLError as error:
        raise ThemePackageError("faceplate YAML is invalid") from error
    return validate_faceplate(value)


def generate_faceplate_css(faceplate: dict[str, Any]) -> str:
    validated = validate_faceplate(faceplate)
    frames: set[str] = set()
    surfaces: set[str] = set()

    def collect(node: dict[str, Any]) -> None:
        if node["type"] == "surface":
            surfaces.add(node["id"])
            return
        frames.add(node["id"])
        for child in node["children"]:
            collect(child)

    for layout in validated["layouts"].values():
        collect(layout["frame"])

    lines = [
        "/* Generated from a coldth.faceplate 0.1 document.",
        " * Faceplate YAML owns layout. This file owns visual treatment.",
        " */",
        "",
        "[data-faceplate] {",
        "  /* Global receiver materials and typography. */",
        "}",
    ]
    for frame in sorted(frames):
        lines.extend(
            [
                "",
                f'[data-frame="{frame}"] {{',
                "  /* Shared chassis, border, background, and ornament. */",
                "}",
            ]
        )
    for surface in sorted(surfaces):
        lines.extend(
            [
                "",
                f'[data-surface="{surface}"] {{',
                "  /* Visual treatment for this trusted Coldth surface. */",
                "}",
            ]
        )
        for part in sorted(SURFACE_PARTS[surface]):
            lines.extend(
                [
                    "",
                    f'[data-surface="{surface}"] [data-part="{part}"] {{',
                    "}",
                ]
            )
    return "\n".join(lines) + "\n"


def _merge_layout(
    parent: dict[str, Any] | None, child: dict[str, Any]
) -> dict[str, Any]:
    if parent is None:
        result = {"regions": [dict(region) for region in child["regions"]]}
        if "groups" in child:
            result["groups"] = [dict(group) for group in child["groups"]]
        if "flow" in child:
            result["flow"] = list(child["flow"])
        if "hidden" in child:
            result["hidden"] = list(child["hidden"])
        if "frame" in child:
            result["frame"] = child["frame"]
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
    groups = child.get("groups", parent.get("groups"))
    if groups is not None:
        result["groups"] = [dict(group) for group in groups]
    flow = child.get("flow", parent.get("flow"))
    if flow is not None:
        result["flow"] = list(flow)
    hidden = child.get("hidden", parent.get("hidden"))
    if hidden is not None:
        result["hidden"] = list(hidden)
    frame = child.get("frame", parent.get("frame"))
    if frame is not None:
        result["frame"] = frame
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
                faceplate_path = manifest.get("faceplate")
                if faceplate_path is not None:
                    faceplate = load_faceplate(
                        (
                            manifest_path.parent
                            / _package_path(
                                faceplate_path,
                                "faceplate",
                                suffixes={".yaml", ".yml"},
                            )
                        ).read_text(encoding="utf-8")
                    )
                    layouts = faceplate["layouts"]
                else:
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
                if manifest.get("faceplate"):
                    faceplate = load_faceplate(
                        (root / manifest["faceplate"]).read_text(encoding="utf-8")
                    )
                    layouts = faceplate["layouts"]
                else:
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
            "faceplateLanguage": (
                FACEPLATE_LANGUAGE if manifest.get("faceplate") else None
            ),
            "faceplateSchemaVersion": (
                FACEPLATE_SCHEMA_VERSION if manifest.get("faceplate") else None
            ),
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
            "faceplateLanguage": (
                descriptor.get("faceplateLanguage")
                or parent.get("faceplateLanguage")
            ),
            "faceplateSchemaVersion": (
                descriptor.get("faceplateSchemaVersion")
                or parent.get("faceplateSchemaVersion")
            ),
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
                if manifest.get("faceplate"):
                    referenced.add(manifest["faceplate"])
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
                if manifest.get("faceplate"):
                    try:
                        load_faceplate(
                            package.read(manifest["faceplate"]).decode("utf-8")
                        )
                    except UnicodeDecodeError as error:
                        raise ThemePackageError(
                            f"Invalid faceplate YAML: {manifest['faceplate']}"
                        ) from error
                else:
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
