from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .model import Preset, ValidationError, flat_bands, validate_balance, validate_bands

DEFAULT_PRIVACY = {"metadata": True, "artwork": False}


class StateStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / "state.json"
        self._lock = threading.RLock()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._state = self._load()
        self._revision = 0

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            state = {
                "bands": flat_bands(),
                "balance": 0,
                "presets": [],
                "privacy": DEFAULT_PRIVACY.copy(),
            }
            self._write(state)
            return state
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            bands = validate_bands(raw.get("bands"))
            balance = validate_balance(raw.get("balance", 0))
            presets = [
                Preset.from_mapping(item).as_dict() for item in raw.get("presets", [])
            ]
            privacy = self._validate_privacy(raw.get("privacy", DEFAULT_PRIVACY))
        except (OSError, json.JSONDecodeError, ValidationError, TypeError) as error:
            raise RuntimeError(f"Invalid Coldth state file {self.path}: {error}") from error
        return {
            "bands": bands,
            "balance": balance,
            "presets": presets,
            "privacy": privacy,
        }

    @staticmethod
    def _validate_privacy(value: Any) -> dict[str, bool]:
        if not isinstance(value, dict):
            raise ValidationError("privacy must be an object")
        unknown = set(value) - set(DEFAULT_PRIVACY)
        if unknown:
            raise ValidationError(
                f"Unknown privacy settings: {', '.join(sorted(unknown))}"
            )
        result = DEFAULT_PRIVACY.copy()
        for name in result:
            setting = value.get(name, result[name])
            if not isinstance(setting, bool):
                raise ValidationError(f"privacy.{name} must be true or false")
            result[name] = setting
        if not result["metadata"]:
            result["artwork"] = False
        return result

    def _write(self, state: dict[str, Any]) -> None:
        payload = json.dumps(state, indent=2, sort_keys=True) + "\n"
        fd, temporary_name = tempfile.mkstemp(
            dir=self.data_dir, prefix=".state-", suffix=".json"
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def bands(self) -> dict[str, float]:
        with self._lock:
            return self._state["bands"].copy()

    def revision(self) -> int:
        with self._lock:
            return self._revision

    def advance_revision(self) -> int:
        with self._lock:
            self._revision += 1
            return self._revision

    def set_bands(self, bands: Any) -> dict[str, float]:
        clean = validate_bands(bands)
        with self._lock:
            self._state["bands"] = clean
            self._write(self._state)
            self._revision += 1
            return clean.copy()

    def balance(self) -> int:
        with self._lock:
            return self._state["balance"]

    def set_balance(self, balance: Any) -> int:
        clean = validate_balance(balance)
        with self._lock:
            self._state["balance"] = clean
            self._write(self._state)
            self._revision += 1
            return clean

    def privacy(self) -> dict[str, bool]:
        with self._lock:
            return self._state["privacy"].copy()

    def set_privacy(self, value: Any) -> dict[str, bool]:
        clean = self._validate_privacy(value)
        with self._lock:
            self._state["privacy"] = clean
            self._write(self._state)
            self._revision += 1
            return clean.copy()

    def presets(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"name": "Flat", "bands": flat_bands()}] + [
                {"name": item["name"], "bands": item["bands"].copy()}
                for item in self._state["presets"]
            ]

    def save_preset(self, value: Any) -> dict[str, Any]:
        preset = Preset.from_mapping(value)
        with self._lock:
            key = preset.name.casefold()
            self._state["presets"] = [
                item
                for item in self._state["presets"]
                if item["name"].casefold() != key
            ]
            self._state["presets"].append(preset.as_dict())
            self._state["presets"].sort(key=lambda item: item["name"].casefold())
            self._write(self._state)
            self._revision += 1
        return preset.as_dict()

    def delete_preset(self, name: str) -> None:
        if name.casefold() == "flat":
            raise ValidationError("Flat cannot be deleted")
        with self._lock:
            before = len(self._state["presets"])
            self._state["presets"] = [
                item
                for item in self._state["presets"]
                if item["name"].casefold() != name.casefold()
            ]
            if len(self._state["presets"]) == before:
                raise KeyError(name)
            self._write(self._state)
            self._revision += 1

    def get_preset(self, name: str) -> dict[str, Any]:
        for preset in self.presets():
            if preset["name"].casefold() == name.casefold():
                return preset
        raise KeyError(name)
