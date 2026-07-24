from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .analyzer import LocalSpectrumAnalyzer
from .camilla import AudioSettings, CamillaClient, SignalLevelClient
from .events import EventBus, utc_timestamp
from .metadata import MetadataTracker, ShairportMetadataAdapter
from .model import (
    BANDS,
    MAX_BALANCE,
    MAX_GAIN,
    MIN_BALANCE,
    MIN_GAIN,
    GAIN_STEP,
    ValidationError,
    flat_bands,
)
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
    analyzer = LocalSpectrumAnalyzer(
        os.getenv("COLDTH_ANALYZER_DEVICE"),
        samplerate=settings.samplerate,
    )
    events = EventBus()
    event_loop: asyncio.AbstractEventLoop | None = None
    shairport_artwork_available = (
        os.getenv("COLDTH_SHAIRPORT_ARTWORK_AVAILABLE", "").lower() == "true"
    )
    metadata = MetadataTracker(
        lambda: store.privacy()["artwork"] and shairport_artwork_available
    )

    def publish_adapter_event(event_type: str, data: dict[str, object]) -> None:
        loop = event_loop
        if loop is not None and loop.is_running():
            store.advance_revision()
            asyncio.run_coroutine_threadsafe(events.publish(event_type, data), loop)

    metadata_adapter = ShairportMetadataAdapter(
        os.getenv("COLDTH_SHAIRPORT_METADATA_PIPE"),
        metadata,
        publish_adapter_event,
        lambda: store.privacy()["metadata"],
    )

    async def reconcile_audio() -> None:
        """Restore the saved config after CamillaDSP is restarted."""
        while True:
            await asyncio.sleep(5)
            status = await asyncio.to_thread(camilla.status)
            if status.get("state") == "Inactive":
                await asyncio.to_thread(camilla.apply, store.bands(), store.balance())

    def meter_frame(stereo: dict[str, Any] | None) -> dict[str, Any]:
        rms = (
            stereo.get("playback_rms")
            or stereo.get("playback_rms_since_last")
            or []
            if stereo
            else []
        )
        peaks = (
            stereo.get("playback_peak")
            or stereo.get("playback_peak_since_last")
            or []
            if stereo
            else []
        )
        return {
            "leftRms": rms[0] if len(rms) > 0 else None,
            "rightRms": rms[1] if len(rms) > 1 else None,
            "leftPeak": peaks[0] if len(peaks) > 0 else None,
            "rightPeak": peaks[1] if len(peaks) > 1 else None,
            "spectrum": analyzer.levels(),
            "timestamp": utc_timestamp(),
        }

    async def publish_meters() -> None:
        while True:
            if events.subscriber_count:
                stereo: dict[str, Any] | None = None
                try:
                    stereo = await asyncio.to_thread(signal_levels.levels)
                except Exception:
                    pass
                await events.publish("meter.frame", meter_frame(stereo))
            await asyncio.sleep(0.1)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        nonlocal event_loop
        event_loop = asyncio.get_running_loop()
        camilla.apply(store.bands(), store.balance())
        analyzer.start()
        metadata_adapter.start()
        reconciler = asyncio.create_task(reconcile_audio())
        meter_publisher = asyncio.create_task(publish_meters())
        try:
            yield
        finally:
            reconciler.cancel()
            meter_publisher.cancel()
            with suppress(asyncio.CancelledError):
                await reconciler
            with suppress(asyncio.CancelledError):
                await meter_publisher
            signal_levels.close()
            metadata_adapter.stop()
            analyzer.stop()
            event_loop = None

    app = FastAPI(
        title="Coldth",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    def engine_name(status: dict[str, Any]) -> str:
        if status.get("online") is not True:
            return "offline"
        state = status.get("state")
        return state.lower() if isinstance(state, str) else "unknown"

    def bit_depth(format_name: str) -> int | None:
        match = re.search(r"\d+", format_name)
        return int(match.group()) if match else None

    def canonical_state() -> dict[str, Any]:
        engine = camilla.status()
        privacy = store.privacy()
        metadata_available = metadata_adapter.configured and privacy["metadata"]
        return {
            "revision": store.revision(),
            "timestamp": utc_timestamp(),
            "capabilities": {
                "eq": True,
                "balance": True,
                "volume": False,
                "presets": True,
                "stereoMeters": True,
                "spectrum": bool(analyzer.device),
                "transport": metadata_available,
                "metadata": metadata_available,
            },
            "tone": {
                "bands": store.bands(),
                "balance": store.balance(),
                "preset": None,
            },
            "audio": {
                "engine": engine_name(engine),
                "sampleRate": settings.samplerate,
                "bitDepth": bit_depth(settings.playback_format),
                "channels": 2,
                "input": "airplay",
                "volume": None,
            },
            "transport": metadata.transport()
            if metadata_available
            else {"state": None, "elapsed": None, "duration": None},
            "metadata": metadata.metadata()
            if metadata_available
            else {
                "artist": None,
                "album": None,
                "title": None,
                "artwork": None,
                "codec": None,
                "bitrate": None,
            },
        }

    async def apply_eq(payload: dict[str, Any]) -> tuple[dict[str, float], bool]:
        try:
            bands = store.set_bands(payload.get("bands"))
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        applied = await asyncio.to_thread(camilla.apply, bands, store.balance())
        await events.publish(
            "tone.changed",
            {"revision": store.revision(), "bands": bands},
        )
        return bands, applied

    async def apply_balance(payload: dict[str, Any]) -> tuple[int, bool]:
        try:
            balance = store.set_balance(payload.get("balance"))
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        applied = await asyncio.to_thread(camilla.apply, store.bands(), balance)
        await events.publish(
            "tone.changed",
            {"revision": store.revision(), "balance": balance},
        )
        return balance, applied

    @app.get("/api/v1/state")
    def get_v1_state() -> dict[str, Any]:
        return canonical_state()

    @app.get("/api/v1/settings")
    def get_v1_settings() -> dict[str, Any]:
        return {
            "privacy": store.privacy(),
            "sources": {
                "shairportMetadata": {
                    "configured": metadata_adapter.configured,
                    "artworkAvailable": shairport_artwork_available,
                }
            },
        }

    @app.put("/api/v1/settings/privacy")
    async def set_v1_privacy(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            privacy = store.set_privacy(payload)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not privacy["metadata"]:
            changes = metadata.clear()
            for event_type, data in changes:
                await events.publish(event_type, data)
        elif not privacy["artwork"]:
            changed = metadata.clear_artwork()
            if changed is not None:
                await events.publish("metadata.changed", changed)
        await events.publish(
            "settings.changed",
            {"revision": store.revision(), "privacy": privacy},
        )
        return {"revision": store.revision(), "privacy": privacy}

    @app.get("/api/v1/artwork/current")
    def get_current_artwork() -> Response:
        if not store.privacy()["metadata"] or not store.privacy()["artwork"]:
            raise HTTPException(status_code=404, detail="Artwork is disabled")
        current = metadata.artwork()
        if current is None:
            raise HTTPException(status_code=404, detail="Artwork is unavailable")
        payload, media_type = current
        return Response(
            content=payload,
            media_type=media_type,
            headers={"Cache-Control": "no-store"},
        )

    @app.put("/api/v1/tone/eq")
    async def set_v1_eq(payload: dict[str, Any]) -> dict[str, Any]:
        bands, applied = await apply_eq(payload)
        return {
            "revision": store.revision(),
            "tone": {"bands": bands},
            "engine": camilla.status(),
            "applied": applied,
        }

    @app.put("/api/v1/tone/balance")
    async def set_v1_balance(payload: dict[str, Any]) -> dict[str, Any]:
        balance, applied = await apply_balance(payload)
        return {
            "revision": store.revision(),
            "tone": {"balance": balance},
            "engine": camilla.status(),
            "applied": applied,
        }

    @app.get("/api/state")
    def get_state() -> dict[str, Any]:
        return {
            "bands": store.bands(),
            "balance": store.balance(),
            "frequencies": list(BANDS),
            "range": {"min": MIN_GAIN, "max": MAX_GAIN, "step": GAIN_STEP},
            "balance_range": {"min": MIN_BALANCE, "max": MAX_BALANCE, "step": 1},
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
                payload["bands"] = analyzer.levels()
                await socket.send_json(payload)
                await asyncio.sleep(0.1)
        except (WebSocketDisconnect, RuntimeError):
            return

    @app.websocket("/api/v1/events")
    async def event_stream(socket: WebSocket) -> None:
        await socket.accept()
        queue = events.subscribe()
        try:
            await socket.send_json(events.envelope("state.snapshot", canonical_state()))
            while True:
                await socket.send_json(await queue.get())
        except (WebSocketDisconnect, RuntimeError):
            return
        finally:
            events.unsubscribe(queue)

    @app.put("/api/eq")
    async def set_eq(payload: dict[str, Any]) -> dict[str, Any]:
        bands, applied = await apply_eq(payload)
        return {"bands": bands, "engine": camilla.status(), "applied": applied}

    @app.put("/api/balance")
    async def set_balance(payload: dict[str, Any]) -> dict[str, Any]:
        balance, applied = await apply_balance(payload)
        return {"balance": balance, "engine": camilla.status(), "applied": applied}

    @app.post("/api/reset")
    def reset() -> dict[str, Any]:
        bands = store.set_bands(flat_bands())
        applied = camilla.apply(bands, store.balance())
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
        applied = camilla.apply(bands, store.balance())
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

    @app.get("/settings", include_in_schema=False)
    def settings_page() -> FileResponse:
        return FileResponse(static_dir / "settings.html")

    return app
