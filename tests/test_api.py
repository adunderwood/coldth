import json
import io
import zipfile

from fastapi.testclient import TestClient

from coldth.app import create_app
from coldth.model import flat_bands


def test_eq_and_preset_round_trip(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        state = client.get("/api/v1/state").json()
        assert state["tone"]["bands"] == flat_bands()

        bands = flat_bands()
        bands["250"] = -2.5
        response = client.put("/api/v1/tone/eq", json={"bands": bands})
        assert response.status_code == 200
        assert response.json()["tone"]["bands"]["250"] == -2.5

        response = client.post(
            "/api/v1/presets", json={"name": "Less boxy", "bands": bands}
        )
        assert response.status_code == 201
        assert [item["name"] for item in client.get("/api/v1/presets").json()] == [
            "Flat",
            "Less boxy",
        ]


def test_invalid_eq_is_rejected(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        bands = flat_bands()
        bands["31"] = 20
        response = client.put("/api/v1/tone/eq", json={"bands": bands})
        assert response.status_code == 422


def test_balance_round_trip(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        response = client.put("/api/v1/tone/balance", json={"balance": -35})

        assert response.status_code == 200
        assert response.json()["tone"]["balance"] == -35
        assert client.get("/api/v1/state").json()["tone"]["balance"] == -35


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


def test_audio_timing_can_be_configured_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("COLDTH_SAMPLE_RATE", "48000")
    monkeypatch.setenv("COLDTH_CHUNKSIZE", "2048")

    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        state = client.get("/api/v1/state").json()

    assert state["audio"]["sampleRate"] == 48000
    config = json.loads((tmp_path / "camilladsp.json").read_text())
    assert config["devices"]["samplerate"] == 48000
    assert config["devices"]["chunksize"] == 2048
    assert config["devices"]["target_level"] == 4096


def test_audio_health_is_available_when_engine_is_offline(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        response = client.get("/api/v1/health/audio")

    assert response.status_code == 200
    health = response.json()
    assert health["engine"] == "offline"
    assert health["pcmFlowing"] is False
    assert health["spectrumFlowing"] is False
    assert health["captureRms"] == []
    assert health["playbackRms"] == []
    assert health["error"]


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


def test_v1_preset_operations_publish_events_and_update_state(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        with client.websocket_connect("/api/v1/events") as socket:
            socket.receive_json()

            def receive(event_type):
                while True:
                    event = socket.receive_json()
                    if event["type"] == event_type:
                        return event

            assert [item["name"] for item in client.get("/api/v1/presets").json()] == [
                "Flat"
            ]

            bands = flat_bands()
            bands["250"] = -3.5
            saved = client.post(
                "/api/v1/presets",
                json={"name": "Less boxy", "bands": bands},
            )
            assert saved.status_code == 201
            assert saved.json()["preset"]["name"] == "Less boxy"
            assert receive("preset.saved")["data"]["preset"]["bands"]["250"] == -3.5

            imported_bands = flat_bands()
            imported_bands["8000"] = 2.0
            imported = client.post(
                "/api/v1/presets/import",
                json={"name": "Air", "bands": imported_bands},
            )
            assert imported.status_code == 201
            assert receive("preset.imported")["data"]["preset"]["name"] == "Air"

            exported = client.get("/api/v1/presets/Less%20boxy/export")
            assert exported.json() == {"name": "Less boxy", "bands": bands}

            loaded = client.post("/api/v1/presets/Less%20boxy/load")
            assert loaded.status_code == 200
            assert loaded.json()["tone"]["preset"] == "Less boxy"
            loaded_event = receive("preset.loaded")
            assert loaded_event["data"]["tone"]["bands"]["250"] == -3.5
            state = client.get("/api/v1/state").json()
            assert state["tone"]["preset"] == "Less boxy"
            assert state["tone"]["bands"]["250"] == -3.5

            deleted = client.delete("/api/v1/presets/Less%20boxy")
            assert deleted.status_code == 204
            assert receive("preset.deleted")["data"]["name"] == "Less boxy"
            assert client.get("/api/v1/state").json()["tone"]["preset"] is None


def test_manual_v1_eq_change_clears_active_preset(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        client.post("/api/v1/presets/Flat/load")
        assert client.get("/api/v1/state").json()["tone"]["preset"] == "Flat"

        bands = flat_bands()
        bands["31"] = 1.0
        response = client.put("/api/v1/tone/eq", json={"bands": bands})

        assert response.json()["tone"]["preset"] is None
        assert client.get("/api/v1/state").json()["tone"]["preset"] is None


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
        themes = client.get("/api/v1/themes").json()

    assert [theme["id"] for theme in themes] == [
        "black-1987",
        "original-yellow",
    ]


def test_v1_theme_package_installation_and_event(tmp_path):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr(
            "manifest.json",
            json.dumps(
                {
                    "id": "com.example.blue",
                    "name": "Blue",
                    "version": "1.0.0",
                    "apiVersion": 1,
                    "styles": "theme.css",
                }
            ),
        )
        package.writestr("theme.css", ":root { --accent: #08f; }\n")

    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        with client.websocket_connect("/api/v1/events") as socket:
            socket.receive_json()
            response = client.post(
                "/api/v1/themes/install",
                content=archive.getvalue(),
                headers={"Content-Type": "application/zip"},
            )
            event = socket.receive_json()

        assert response.status_code == 201
        assert response.json()["theme"]["id"] == "com.example.blue"
        assert event["type"] == "theme.installed"
        assert event["data"]["theme"]["id"] == "com.example.blue"
        themes = client.get("/api/v1/themes").json()
        assert "com.example.blue" in {theme["id"] for theme in themes}
        asset = client.get(
            "/api/v1/themes/com.example.blue/assets/theme.css"
        )
        assert asset.status_code == 200
        assert asset.text == ":root { --accent: #08f; }\n"
        assert client.post(
            "/api/v1/themes/install", content=archive.getvalue()
        ).status_code == 409


def test_v1_theme_install_rejects_invalid_archive(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        response = client.post("/api/v1/themes/install", content=b"not a zip")

    assert response.status_code == 422
    assert not (tmp_path / "themes" / "com.example.bad").exists()


def test_unversioned_api_is_not_exposed(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        for path in (
            "/api/state",
            "/api/eq",
            "/api/balance",
            "/api/presets",
            "/api/meters",
            "/api/themes",
        ):
            assert client.get(path).status_code == 404
