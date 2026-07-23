from __future__ import annotations

import os
import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .camilla import AudioSettings, CamillaClient, SignalLevelClient, SpectrumClient
from .model import BANDS, MAX_GAIN, MIN_GAIN, GAIN_STEP, ValidationError, flat_bands
from .store import StateStore
from .themes import ThemeRegistry


def create_app(
    data_dir: Path | None = None,
    camilla_url: str | None = None,
    audio_settings: AudioSettings | None = None,
) -> FastAPI:
    root = data_dir or Path(os.getenv("COLDTH_DATA_DIR", "data"))
    store = StateStore(root)
    settings = audio_settings or AudioSettings(
        capture_device=os.getenv("COLDTH_CAPTURE_DEVICE", "hw:Loopback,1,0"),
        playback_device=os.getenv("COLDTH_PLAYBACK_DEVICE", "hw:Headphones,0"),
        capture_format=os.getenv("COLDTH_CAPTURE_FORMAT", "S16LE"),
        playback_format=os.getenv("COLDTH_PLAYBACK_FORMAT", "S16LE"),
    )
    engine_url = camilla_url or os.getenv(
        "COLDTH_CAMILLADSP_URL", "ws://127.0.0.1:1234"
    )
    camilla = CamillaClient(
        engine_url,
        root / "camilladsp.json",
        settings,
    )
    signal_levels = SignalLevelClient(engine_url)
    static_dir = Path(__file__).parent / "static"
    themes = ThemeRegistry(static_dir / "themes")
    spectrum = SpectrumClient(
        os.getenv("COLDTH_SPECTRUM_URL", "ws://127.0.0.1:1235")
    )

    async def reconcile_audio() -> None:
        """Restore the saved config after CamillaDSP is restarted."""
        while True:
            await asyncio.sleep(5)
            status = await asyncio.to_thread(camilla.status)
            if status.get("state") == "Inactive":
                await asyncio.to_thread(camilla.apply, store.bands())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        camilla.apply(store.bands())
        reconciler = asyncio.create_task(reconcile_audio())
        try:
            yield
        finally:
            reconciler.cancel()
            with suppress(asyncio.CancelledError):
                await reconciler
            signal_levels.close()
            spectrum.close()

    app = FastAPI(
        title="Coldth",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.get("/api/state")
    def get_state() -> dict[str, Any]:
        return {
            "bands": store.bands(),
            "frequencies": list(BANDS),
            "range": {"min": MIN_GAIN, "max": MAX_GAIN, "step": GAIN_STEP},
            "engine": camilla.status(),
        }

    @app.get("/api/themes")
    def get_themes() -> list[dict[str, Any]]:
        return themes.list()

    @app.websocket("/api/meters")
    async def meters(socket: WebSocket) -> None:
        await socket.accept()
        try:
            while True:
                payload: dict[str, Any] = {"stereo": None, "bands": None}
                try:
                    payload["stereo"] = await asyncio.to_thread(signal_levels.levels)
                except Exception:
                    pass
                payload["bands"] = await asyncio.to_thread(spectrum.levels)
                await socket.send_json(payload)
                await asyncio.sleep(0.1)
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.put("/api/eq")
    def set_eq(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            bands = store.set_bands(payload.get("bands"))
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        applied = camilla.apply(bands)
        return {"bands": bands, "engine": camilla.status(), "applied": applied}

    @app.post("/api/reset")
    def reset() -> dict[str, Any]:
        bands = store.set_bands(flat_bands())
        applied = camilla.apply(bands)
        return {"bands": bands, "engine": camilla.status(), "applied": applied}

    @app.get("/api/presets")
    def get_presets() -> list[dict[str, Any]]:
        return store.presets()

    @app.post("/api/presets", status_code=201)
    def save_preset(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return store.save_preset(payload)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/presets/import", status_code=201)
    def import_preset(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return store.save_preset(payload)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/presets/{name}/export")
    def export_preset(name: str) -> dict[str, Any]:
        try:
            return store.get_preset(unquote(name))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Preset not found") from error

    @app.post("/api/presets/{name}/load")
    def load_preset(name: str) -> dict[str, Any]:
        try:
            preset = store.get_preset(unquote(name))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Preset not found") from error
        bands = store.set_bands(preset["bands"])
        applied = camilla.apply(bands)
        return {"bands": bands, "engine": camilla.status(), "applied": applied}

    @app.delete("/api/presets/{name}", status_code=204)
    def delete_preset(name: str) -> None:
        try:
            store.delete_preset(unquote(name))
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Preset not found") from error

    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return app
