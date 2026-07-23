from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ThemeRegistry:
    def __init__(self, root: Path):
        self.root = root

    def list(self) -> list[dict[str, Any]]:
        themes: list[dict[str, Any]] = []
        for manifest_path in sorted(self.root.glob("*/theme.json")):
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
                    "stylesheet": f"/assets/themes/{theme_id}/theme.css",
                }
            )
        return themes
