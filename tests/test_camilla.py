import json

import pytest

from coldth.camilla import (
    AudioSettings,
    CamillaClient,
    PersistentCamillaClient,
    SignalLevelClient,
    SpectrumClient,
    build_config,
)
from coldth.model import flat_bands


def test_config_has_stereo_ten_band_pipeline_and_headroom():
    bands = flat_bands()
    bands["62"] = 4
    config = build_config(bands)

    assert config["filters"]["coldth_headroom"]["parameters"]["gain"] == -4
    assert config["filters"]["coldth_62"]["parameters"]["gain"] == 4
    assert config["pipeline"][0]["channels"] == [0, 1]
    assert len(config["pipeline"][0]["names"]) == 11


def test_balance_attenuates_only_the_opposite_channel():
    config = build_config(flat_bands(), balance=50)

    left = config["filters"]["coldth_balance_left"]["parameters"]["gain"]
    right = config["filters"]["coldth_balance_right"]["parameters"]["gain"]

    assert left == pytest.approx(-6.0206)
    assert right == 0
    assert config["pipeline"][1]["channels"] == [0]
    assert config["pipeline"][2]["channels"] == [1]


def test_audio_devices_are_configurable():
    config = build_config(
        flat_bands(),
        AudioSettings(
            capture_device="capture",
            playback_device="playback",
            capture_format="S16LE",
            playback_format="S24LE",
        ),
    )
    assert config["devices"]["capture"]["device"] == "capture"
    assert config["devices"]["playback"]["device"] == "playback"
    assert config["devices"]["capture"]["format"] == "S16LE"
    assert config["devices"]["playback"]["format"] == "S24LE"


def test_offline_engine_still_writes_reboot_config(tmp_path):
    path = tmp_path / "camilladsp.json"
    client = CamillaClient("ws://127.0.0.1:1", path, timeout=0.01)

    assert client.apply(flat_bands()) is False
    assert json.loads(path.read_text())["title"] == "Coldth"
    assert client.status()["online"] is False
    assert client.status()["apply_error"]


def test_signal_levels_are_unwrapped(tmp_path):
    client = SignalLevelClient("unused")
    client._client.command = lambda _: {
        "GetSignalLevels": {
            "result": "Ok",
            "value": {"playback_rms": [-18.0, -17.5]},
        }
    }

    assert client.levels()["playback_rms"] == [-18.0, -17.5]


def test_inactive_engine_is_not_reported_online(tmp_path):
    client = CamillaClient("unused", tmp_path / "config.json")
    client._command = lambda _: {
        "GetState": {"result": "Ok", "value": "Inactive"}
    }

    status = client.status()

    assert status["online"] is False
    assert status["state"] == "Inactive"
    assert "inactive" in status["error"]


def test_spectrum_requires_exactly_ten_channels():
    spectrum = SpectrumClient("unused")
    spectrum._client.command = lambda _: {
        "GetPlaybackSignalRms": {"result": "Ok", "value": [-24.0] * 10}
    }
    assert spectrum.levels() == [-24.0] * 10

    spectrum._client.command = lambda _: {
        "GetPlaybackSignalRms": {"result": "Ok", "value": [-24.0] * 9}
    }
    assert spectrum.levels() is None


def test_meter_client_reuses_websocket(monkeypatch):
    class FakeConnection:
        def __init__(self):
            self.sent = []
            self.closed = False

        def send(self, value):
            self.sent.append(value)

        def recv(self):
            return '{"GetSignalLevels":{"result":"Ok","value":{}}}'

        def close(self):
            self.closed = True

    connection = FakeConnection()
    connections = []

    def connect(*_, **__):
        connections.append(connection)
        return connection

    monkeypatch.setattr("coldth.camilla.websocket.create_connection", connect)
    client = PersistentCamillaClient("ws://unused")

    client.command("GetSignalLevels")
    client.command("GetSignalLevels")
    client.close()

    assert connections == [connection]
    assert len(connection.sent) == 2
    assert connection.closed is True
