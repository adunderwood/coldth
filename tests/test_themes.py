import json

from coldth.themes import ThemeRegistry


def test_registry_ignores_invalid_manifests(tmp_path):
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
            "stylesheet": "/assets/themes/valid/theme.css",
        }
    ]
