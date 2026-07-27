import io
import json
import stat
import zipfile

import pytest

from coldth.themes import (
    ThemeAlreadyInstalledError,
    ThemePackageError,
    ThemeRegistry,
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
            "/api/v1/themes/com.example.magenta/assets/theme.css"
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


def test_theme_inheritance_is_rejected_until_activation_support_exists(tmp_path):
    builtins = tmp_path / "builtins"
    builtins.mkdir()
    registry = ThemeRegistry(builtins, tmp_path / "installed")
    manifest = {
        "id": "com.example.child",
        "name": "Child",
        "version": "1.0.0",
        "apiVersion": 1,
        "extends": "com.example.parent",
        "styles": "theme.css",
    }

    with pytest.raises(ThemePackageError, match="inheritance is not active"):
        registry.install(theme_archive(manifest=manifest))
