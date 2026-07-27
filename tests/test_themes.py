import io
import json
import stat
import zipfile

import pytest

from coldth.themes import (
    ThemeAlreadyInstalledError,
    ThemeDependencyError,
    ThemePackageError,
    ThemeRegistry,
    ThemeVersionError,
    validate_layout,
    validate_manifest,
)


def theme_archive(
    *,
    manifest=None,
    css=b":root { --accent: #f0f; }\n",
    extra=None,
):
    manifest = manifest or {
        "id": "com.example.magenta",
        "name": "Magenta",
        "version": "1.0.0",
        "apiVersion": 1,
        "styles": "theme.css",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("manifest.json", json.dumps(manifest))
        package.writestr("theme.css", css)
        for name, value in (extra or {}).items():
            package.writestr(name, value)
    return output.getvalue()


def test_registry_ignores_invalid_builtin_manifests(tmp_path):
    valid = tmp_path / "valid"
    valid.mkdir()
    (valid / "theme.json").write_text(
        json.dumps({"id": "valid", "name": "Valid"}), encoding="utf-8"
    )
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "theme.json").write_text("{", encoding="utf-8")

    assert ThemeRegistry(tmp_path).list() == [
        {
            "id": "valid",
            "name": "Valid",
            "description": "",
            "version": None,
            "builtin": True,
            "stylesheet": "/assets/themes/valid/theme.css",
        }
    ]


def test_builtin_descriptor_loads_a_validated_layout(tmp_path):
    theme = tmp_path / "black"
    theme.mkdir()
    (theme / "theme.json").write_text(
        json.dumps(
            {
                "id": "black",
                "name": "Black",
                "layouts": {"landscape": "landscape.json"},
            }
        ),
        encoding="utf-8",
    )
    (theme / "landscape.json").write_text(
        json.dumps(
            {
                "regions": [
                    {
                        "id": "tone-bank",
                        "component": "tone-bank",
                        "presentation": "coldth.presentation/fader-ladder@1",
                        "options": {"orientation": "vertical", "segments": 24},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    descriptor = ThemeRegistry(tmp_path).descriptor("black")

    assert descriptor["layouts"]["landscape"]["regions"][0]["component"] == (
        "tone-bank"
    )


def test_theme_package_installs_atomically_and_serves_assets(tmp_path):
    builtins = tmp_path / "builtins"
    installed = tmp_path / "installed"
    builtins.mkdir()
    registry = ThemeRegistry(builtins, installed)

    theme = registry.install(
        theme_archive(
            css=b".meter { background: url(assets/glow.png); }\n",
            extra={"assets/glow.png": b"\x89PNG\r\n\x1a\n"},
        )
    )

    assert theme == {
        "id": "com.example.magenta",
        "name": "Magenta",
        "description": "",
        "version": "1.0.0",
        "builtin": False,
        "stylesheet": (
            "/api/v1/themes/com.example.magenta/assets/theme.css?v=1.0.0"
        ),
    }
    assert registry.asset("com.example.magenta", "theme.css").read_text() == (
        ".meter { background: url(assets/glow.png); }\n"
    )
    assert not list(installed.glob(".theme-*"))
    with pytest.raises(ThemeAlreadyInstalledError):
        registry.install(theme_archive())


def test_descriptor_exposes_validated_tokens_and_layouts(tmp_path):
    builtins = tmp_path / "builtins"
    installed = tmp_path / "installed"
    builtins.mkdir()
    registry = ThemeRegistry(builtins, installed)
    manifest = {
        "id": "com.example.magenta",
        "name": "Magenta",
        "version": "1.0.0",
        "apiVersion": 1,
        "styles": "theme.css",
        "tokens": {"receiver.accent": "#ff00ff"},
        "layouts": {"portrait": "layouts/portrait.json"},
    }
    layout = {
        "regions": [
            {
                "id": "tone",
                "component": "eq",
                "presentation": "coldth.presentation/vertical-fader@1",
                "options": {"orientation": "horizontal"},
            }
        ]
    }
    registry.install(
        theme_archive(
            manifest=manifest,
            extra={"layouts/portrait.json": json.dumps(layout)},
        )
    )

    descriptor = registry.descriptor("com.example.magenta")

    assert descriptor["apiVersion"] == 1
    assert descriptor["tokens"] == {"receiver.accent": "#ff00ff"}
    assert descriptor["layouts"]["portrait"] == layout


@pytest.mark.parametrize(
    "name",
    ("../escape.css", "/absolute.css", r"assets\windows.css"),
)
def test_theme_package_rejects_unsafe_archive_paths(tmp_path, name):
    builtins = tmp_path / "builtins"
    builtins.mkdir()
    registry = ThemeRegistry(builtins, tmp_path / "installed")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("manifest.json", "{}")
        package.writestr(name, "bad")

    with pytest.raises(ThemePackageError, match="Unsafe archive path"):
        registry.install(output.getvalue())
    assert not list((tmp_path / "installed").glob("com.*"))


def test_theme_package_rejects_symlinks(tmp_path):
    builtins = tmp_path / "builtins"
    builtins.mkdir()
    registry = ThemeRegistry(builtins, tmp_path / "installed")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("manifest.json", "{}")
        link = zipfile.ZipInfo("theme.css")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        package.writestr(link, "target.css")

    with pytest.raises(ThemePackageError, match="symlinks"):
        registry.install(output.getvalue())


@pytest.mark.parametrize(
    "css, message",
    (
        (b'@import "https://example.com/theme.css";', "imports"),
        (b"body { background: url(https://example.com/a.png); }", "Unsafe CSS"),
        (b"body { background: url(assets/missing.png); }", "missing asset"),
    ),
)
def test_theme_package_rejects_unsafe_css(tmp_path, css, message):
    builtins = tmp_path / "builtins"
    builtins.mkdir()
    registry = ThemeRegistry(builtins, tmp_path / "installed")

    with pytest.raises(ThemePackageError, match=message):
        registry.install(theme_archive(css=css))


def test_manifest_contract_is_strict():
    with pytest.raises(ThemePackageError, match="reserved"):
        validate_manifest(
            {
                "id": "coldth.impostor",
                "name": "No",
                "version": "1.0.0",
                "apiVersion": 1,
                "styles": "theme.css",
            }
        )
    with pytest.raises(ThemePackageError, match="apiVersion"):
        validate_manifest(
            {
                "id": "com.example.future",
                "name": "Future",
                "version": "1.0.0",
                "apiVersion": 2,
                "styles": "theme.css",
            }
        )


def test_layout_rejects_incompatible_presentations_and_options():
    with pytest.raises(ThemePackageError, match="incompatible"):
        validate_layout(
            {
                "regions": [
                    {
                        "id": "balance",
                        "component": "balance",
                        "presentation": "coldth.presentation/led-bar@1",
                    }
                ]
            }
        )
    with pytest.raises(ThemePackageError, match="Unknown layout surface"):
        validate_layout(
            {
                "regions": [
                    {
                        "id": "tone",
                        "component": "eq",
                        "presentation": "coldth.presentation/vertical-fader@1",
                    }
                ],
                "flow": ["tone", "transport"],
            }
        )
    with pytest.raises(ThemePackageError, match="unique array"):
        validate_layout(
            {
                "regions": [
                    {
                        "id": "tone",
                        "component": "eq",
                        "presentation": "coldth.presentation/vertical-fader@1",
                    }
                ],
                "flow": ["tone", "tone"],
            }
        )
    with pytest.raises(ThemePackageError, match="cannot be hidden"):
        validate_layout(
            {
                "regions": [
                    {
                        "id": "tone",
                        "component": "eq",
                        "presentation": "coldth.presentation/vertical-fader@1",
                    }
                ],
                "hidden": ["balance"],
            }
        )
    with pytest.raises(ThemePackageError, match="Unknown option"):
        validate_layout(
            {
                "regions": [
                    {
                        "id": "tone",
                        "component": "eq",
                        "presentation": "coldth.presentation/vertical-fader@1",
                        "options": {"rotationSpeed": 12},
                    }
                ]
            }
        )
    with pytest.raises(ThemePackageError, match="out of range"):
        validate_layout(
            {
                "regions": [
                    {
                        "id": "tone-bank",
                        "component": "tone-bank",
                        "presentation": "coldth.presentation/fader-ladder@1",
                        "options": {"segments": 80},
                    }
                ]
            }
        )


def test_theme_inheritance_resolves_css_tokens_and_layout_regions(tmp_path):
    builtins = tmp_path / "builtins"
    builtins.mkdir()
    parent = builtins / "parent"
    parent.mkdir()
    (parent / "theme.css").write_text(":root { --parent: 1; }", encoding="utf-8")
    (parent / "theme.json").write_text(
        json.dumps(
            {
                "id": "parent",
                "name": "Parent",
                "tokens": {
                    "receiver.panel": "#111111",
                    "receiver.accent": "#00ff00",
                },
                "layouts": {"landscape": "landscape.json"},
            }
        ),
        encoding="utf-8",
    )
    (parent / "landscape.json").write_text(
        json.dumps(
            {
                "regions": [
                    {
                        "id": "tone",
                        "component": "eq",
                        "presentation": "coldth.presentation/vertical-fader@1",
                        "options": {"orientation": "vertical"},
                    },
                    {
                        "id": "balance",
                        "component": "balance",
                        "presentation": (
                            "coldth.presentation/horizontal-slider@1"
                        ),
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = ThemeRegistry(builtins, tmp_path / "installed")
    manifest = {
        "id": "com.example.child",
        "name": "Child",
        "version": "1.0.0",
        "apiVersion": 1,
        "extends": "parent",
        "styles": "theme.css",
        "tokens": {"receiver.accent": "#ff00ff"},
        "layouts": {"landscape": "child.json"},
    }
    child_layout = {
        "regions": [
            {
                "id": "tone",
                "component": "tone-bank",
                "presentation": "coldth.presentation/fader-ladder@1",
                "options": {"segments": 18},
            }
        ],
        "flow": ["tone", "meters", "balance", "presets"],
        "hidden": ["spectrum"],
    }

    registry.install(
        theme_archive(
            manifest=manifest,
            extra={"child.json": json.dumps(child_layout)},
        )
    )
    descriptor = registry.descriptor("com.example.child")

    assert descriptor["lineage"] == ["parent", "com.example.child"]
    assert descriptor["stylesheets"] == [
        "/assets/themes/parent/theme.css",
        "/api/v1/themes/com.example.child/assets/theme.css?v=1.0.0",
    ]
    assert descriptor["tokens"] == {
        "receiver.panel": "#111111",
        "receiver.accent": "#ff00ff",
    }
    assert [region["id"] for region in descriptor["layouts"]["landscape"]["regions"]] == [
        "tone",
        "balance",
    ]
    assert descriptor["layouts"]["landscape"]["regions"][0]["component"] == (
        "tone-bank"
    )
    assert descriptor["layouts"]["landscape"]["flow"] == [
        "tone",
        "meters",
        "balance",
        "presets",
    ]
    assert descriptor["layouts"]["landscape"]["hidden"] == ["spectrum"]


def test_theme_inheritance_rejects_missing_parent(tmp_path):
    builtins = tmp_path / "builtins"
    builtins.mkdir()
    registry = ThemeRegistry(builtins, tmp_path / "installed")
    manifest = {
        "id": "com.example.child",
        "name": "Child",
        "version": "1.0.0",
        "apiVersion": 1,
        "extends": "com.example.missing",
        "styles": "theme.css",
    }

    with pytest.raises(ThemePackageError, match="Parent theme is not installed"):
        registry.install(theme_archive(manifest=manifest))


def test_theme_inheritance_detects_cycles_in_existing_store(tmp_path):
    builtins = tmp_path / "builtins"
    installed = tmp_path / "installed"
    builtins.mkdir()
    installed.mkdir()
    for theme_id, parent in (
        ("com.example.one", "com.example.two"),
        ("com.example.two", "com.example.one"),
    ):
        root = installed / theme_id
        root.mkdir()
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "id": theme_id,
                    "name": theme_id,
                    "version": "1.0.0",
                    "apiVersion": 1,
                    "extends": parent,
                    "styles": "theme.css",
                }
            ),
            encoding="utf-8",
        )
        (root / "theme.css").write_text("", encoding="utf-8")

    with pytest.raises(ThemePackageError, match="inheritance cycle"):
        ThemeRegistry(builtins, installed).descriptor("com.example.one")


def test_theme_update_replaces_installed_copy_and_uninstalls(tmp_path):
    builtins = tmp_path / "builtins"
    builtins.mkdir()
    registry = ThemeRegistry(builtins, tmp_path / "installed")
    registry.install(theme_archive(css=b":root { --generation: one; }"))
    update_manifest = {
        "id": "com.example.magenta",
        "name": "Magenta",
        "version": "2.0.0",
        "apiVersion": 1,
        "styles": "theme.css",
    }

    result = registry.install_result(
        theme_archive(
            manifest=update_manifest,
            css=b":root { --generation: two; }",
        )
    )

    assert result["operation"] == "updated"
    assert result["previousVersion"] == "1.0.0"
    assert result["theme"]["version"] == "2.0.0"
    assert registry.asset(
        "com.example.magenta", "theme.css"
    ).read_text() == ":root { --generation: two; }"
    assert not (tmp_path / "installed" / "com.example.magenta" / "versions").exists()

    with pytest.raises(ThemeVersionError, match="newer than 2.0.0"):
        registry.install(theme_archive())
    assert registry.asset(
        "com.example.magenta", "theme.css"
    ).read_text() == ":root { --generation: two; }"

    removed = registry.uninstall("com.example.magenta")

    assert removed["version"] == "2.0.0"
    assert registry.list() == []


def test_theme_uninstall_rejects_installed_dependents(tmp_path):
    builtins = tmp_path / "builtins"
    builtins.mkdir()
    registry = ThemeRegistry(builtins, tmp_path / "installed")
    registry.install(theme_archive())
    child_manifest = {
        "id": "com.example.child",
        "name": "Child",
        "version": "1.0.0",
        "apiVersion": 1,
        "extends": "com.example.magenta",
        "styles": "theme.css",
    }
    registry.install(theme_archive(manifest=child_manifest))

    with pytest.raises(ThemeDependencyError, match="com.example.child"):
        registry.uninstall("com.example.magenta")


def test_theme_update_replaces_existing_flat_install(tmp_path):
    builtins = tmp_path / "builtins"
    installed = tmp_path / "installed"
    builtins.mkdir()
    legacy = installed / "com.example.magenta"
    legacy.mkdir(parents=True)
    legacy_manifest = {
        "id": "com.example.magenta",
        "name": "Magenta",
        "version": "1.0.0",
        "apiVersion": 1,
        "styles": "theme.css",
    }
    (legacy / "manifest.json").write_text(
        json.dumps(legacy_manifest), encoding="utf-8"
    )
    (legacy / "theme.css").write_text("legacy", encoding="utf-8")
    registry = ThemeRegistry(builtins, installed)
    update_manifest = {**legacy_manifest, "version": "1.1.0"}

    result = registry.install_result(theme_archive(manifest=update_manifest))

    assert result["theme"]["version"] == "1.1.0"
    assert (
        installed / "com.example.magenta" / "theme.css"
    ).read_text() == ":root { --accent: #f0f; }\n"
    assert not (installed / "com.example.magenta" / "versions").exists()
