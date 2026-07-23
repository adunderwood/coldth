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


def test_two_builtin_themes_are_available(tmp_path):
    with TestClient(
        create_app(data_dir=tmp_path, camilla_url="ws://127.0.0.1:1")
    ) as client:
        themes = client.get("/api/themes").json()

    assert [theme["id"] for theme in themes] == [
        "black-1987",
        "original-yellow",
    ]
