import json

import pytest

from coldth.model import ValidationError, flat_bands
from coldth.store import StateStore


def test_state_survives_reopen(tmp_path):
    store = StateStore(tmp_path)
    bands = flat_bands()
    bands["62"] = -2
    store.set_bands(bands)

    assert StateStore(tmp_path).bands()["62"] == -2
    assert json.loads((tmp_path / "state.json").read_text())["bands"]["62"] == -2


def test_flat_is_the_only_built_in_preset(tmp_path):
    store = StateStore(tmp_path)
    assert store.presets() == [{"name": "Flat", "bands": flat_bands()}]
    with pytest.raises(ValidationError):
        store.delete_preset("Flat")


def test_user_preset_can_be_replaced_and_deleted(tmp_path):
    store = StateStore(tmp_path)
    first = flat_bands()
    first["125"] = -3
    store.save_preset({"name": "Speakers", "bands": first})
    second = flat_bands()
    second["125"] = -2
    store.save_preset({"name": "speakers", "bands": second})

    assert len(store.presets()) == 2
    assert store.get_preset("SPEAKERS")["bands"]["125"] == -2
    store.delete_preset("speakers")
    assert len(store.presets()) == 1
