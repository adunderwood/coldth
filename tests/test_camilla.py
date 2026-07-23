import json

from coldth.camilla import AudioSettings, CamillaClient, build_config
from coldth.model import flat_bands


def test_config_has_stereo_ten_band_pipeline_and_headroom():
    bands = flat_bands()
    bands["62"] = 4
    config = build_config(bands)

    assert config["filters"]["coldth_headroom"]["parameters"]["gain"] == -4
    assert config["filters"]["coldth_62"]["parameters"]["gain"] == 4
    assert config["pipeline"][0]["channels"] == [0, 1]
    assert len(config["pipeline"][0]["names"]) == 11


def test_audio_devices_are_configurable():
    config = build_config(
        flat_bands(),
        AudioSettings(capture_device="capture", playback_device="playback"),
    )
    assert config["devices"]["capture"]["device"] == "capture"
    assert config["devices"]["playback"]["device"] == "playback"


def test_offline_engine_still_writes_reboot_config(tmp_path):
    path = tmp_path / "camilladsp.json"
    client = CamillaClient("ws://127.0.0.1:1", path, timeout=0.01)

    assert client.apply(flat_bands()) is False
    assert json.loads(path.read_text())["title"] == "Coldth"
    assert client.status()["online"] is False
