from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

BANDS = (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
MIN_GAIN = -12.0
MAX_GAIN = 12.0
GAIN_STEP = 0.5
MIN_BALANCE = -100
MAX_BALANCE = 100


class ValidationError(ValueError):
    pass


def flat_bands() -> dict[str, float]:
    return {str(frequency): 0.0 for frequency in BANDS}


def validate_name(value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError("Preset name must be text")
    name = value.strip()
    if not name:
        raise ValidationError("Preset name cannot be empty")
    if len(name) > 80:
        raise ValidationError("Preset name must be 80 characters or fewer")
    if name.casefold() == "flat":
        raise ValidationError("Flat is reserved for the built-in preset")
    return name


def validate_bands(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValidationError("bands must be an object")
    expected = {str(frequency) for frequency in BANDS}
    if set(value) != expected:
        raise ValidationError("bands must contain exactly the ten Coldth frequencies")

    result: dict[str, float] = {}
    for frequency in BANDS:
        raw_gain = value[str(frequency)]
        if isinstance(raw_gain, bool) or not isinstance(raw_gain, (int, float)):
            raise ValidationError(f"{frequency} Hz gain must be a number")
        gain = float(raw_gain)
        if not MIN_GAIN <= gain <= MAX_GAIN:
            raise ValidationError(
                f"{frequency} Hz gain must be between {MIN_GAIN:g} and {MAX_GAIN:g} dB"
            )
        steps = round(gain / GAIN_STEP)
        if abs(gain - steps * GAIN_STEP) > 1e-9:
            raise ValidationError(
                f"{frequency} Hz gain must use {GAIN_STEP:g} dB increments"
            )
        result[str(frequency)] = steps * GAIN_STEP
    return result


def validate_balance(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("balance must be a number")
    balance = int(value)
    if balance != value or not MIN_BALANCE <= balance <= MAX_BALANCE:
        raise ValidationError("balance must be a whole number between -100 and 100")
    return balance


@dataclass(frozen=True)
class Preset:
    name: str
    bands: dict[str, float]

    @classmethod
    def from_mapping(cls, value: Any) -> "Preset":
        if not isinstance(value, Mapping):
            raise ValidationError("Preset must be an object")
        unknown = set(value) - {"name", "bands"}
        if unknown:
            raise ValidationError(f"Unknown preset fields: {', '.join(sorted(unknown))}")
        return cls(
            name=validate_name(value.get("name")),
            bands=validate_bands(value.get("bands")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "bands": self.bands.copy()}
