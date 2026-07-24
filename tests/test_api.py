from fastapi.testclient import TestClient

from coldth.app import create_app
from coldth.model import flat_bands


def test_eq_and_preset_round_trip(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        state = client.get("/api/state").json()
        assert state["bands"] == flat_bands()

        bands = flat_bands()
        bands["250"] = -2.5
        response = client.put("/api/eq", json={"bands": bands})
        assert response.status_code == 200
        assert response.json()["bands"]["250"] == -2.5

        response = client.post(
            "/api/presets", json={"name": "Less boxy", "bands": bands}
        )
        assert response.status_code == 201
        assert [item["name"] for item in client.get("/api/presets").json()] == [
            "Flat",
            "Less boxy",
        ]


def test_invalid_eq_is_rejected(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        bands = flat_bands()
        bands["31"] = 20
        response = client.put("/api/eq", json={"bands": bands})
        assert response.status_code == 422


def test_balance_round_trip(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        response = client.put("/api/balance", json={"balance": -35})

        assert response.status_code == 200
        assert response.json()["balance"] == -35
        assert client.get("/api/state").json()["balance"] == -35


def test_v1_state_and_tone_commands_share_canonical_state(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        state = client.get("/api/v1/state")

        assert state.status_code == 200
        assert state.json()["revision"] == 0
        assert state.json()["tone"] == {
            "bands": flat_bands(),
            "balance": 0,
            "preset": None,
        }
        assert state.json()["capabilities"]["eq"] is True
        assert state.json()["capabilities"]["spectrum"] is False
        assert state.json()["audio"]["engine"] == "offline"
        assert state.json()["audio"]["sampleRate"] == 44100
        assert state.json()["audio"]["bitDepth"] == 16
        assert state.json()["timestamp"].endswith("Z")

        bands = flat_bands()
        bands["1000"] = 1.5
        eq = client.put("/api/v1/tone/eq", json={"bands": bands})
        balance = client.put("/api/v1/tone/balance", json={"balance": 12})

        assert eq.status_code == 200
        assert eq.json()["revision"] == 1
        assert eq.json()["tone"]["bands"]["1000"] == 1.5
        assert balance.status_code == 200
        assert balance.json()["revision"] == 2
        assert balance.json()["tone"]["balance"] == 12

        current = client.get("/api/v1/state").json()
        assert current["revision"] == 2
        assert current["tone"]["bands"]["1000"] == 1.5
        assert current["tone"]["balance"] == 12
        assert client.get("/api/state").json()["balance"] == 12


def test_v1_event_stream_sends_snapshot_and_tone_changes(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        with client.websocket_connect("/api/v1/events") as socket:
            snapshot = socket.receive_json()

            assert snapshot["type"] == "state.snapshot"
            assert snapshot["data"]["revision"] == 0
            assert snapshot["data"]["tone"]["balance"] == 0

            response = client.put("/api/v1/tone/balance", json={"balance": -18})
            assert response.status_code == 200

            while True:
                event = socket.receive_json()
                if event["type"] == "tone.changed":
                    break

            assert event["seq"] > snapshot["seq"]
            assert event["data"] == {"revision": 1, "balance": -18}
            assert event["timestamp"].endswith("Z")

            while event["type"] != "meter.frame":
                event = socket.receive_json()

            assert event["data"] == {
                "leftRms": None,
                "rightRms": None,
                "leftPeak": None,
                "rightPeak": None,
                "spectrum": None,
                "timestamp": event["data"]["timestamp"],
            }


def test_privacy_settings_default_to_text_only_and_persist(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        settings = client.get("/api/v1/settings").json()
        assert settings["privacy"] == {"metadata": True, "artwork": False}
        assert settings["sources"]["shairportMetadata"]["configured"] is False

        response = client.put(
            "/api/v1/settings/privacy",
            json={"metadata": False, "artwork": True},
        )
        assert response.status_code == 200
        assert response.json()["privacy"] == {"metadata": False, "artwork": False}
        assert client.get("/api/v1/state").json()["capabilities"]["metadata"] is False
        assert client.get("/api/v1/artwork/current").status_code == 404

    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        assert client.get("/api/v1/settings").json()["privacy"] == {
            "metadata": False,
            "artwork": False,
        }


def test_settings_page_is_available(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        response = client.get("/settings")

    assert response.status_code == 200
    assert "Use album artwork" in response.text


def test_two_builtin_themes_are_available(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        themes = client.get("/api/themes").json()

    assert [theme["id"] for theme in themes] == [
        "black-1987",
        "original-yellow",
    ]
