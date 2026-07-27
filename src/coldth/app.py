from __future__ import annotations

import asyncio
import logging
import math
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
)
from .store import StateStore
from .themes import ThemeRegistry

logger = logging.getLogger("coldth.audio")


def _positive_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


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
        samplerate=_positive_env_int("COLDTH_SAMPLE_RATE", 44100),
        chunksize=_positive_env_int("COLDTH_CHUNKSIZE", 1024),
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
    metadata = MetadataTracker(lambda: store.privacy()["artwork"])

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
        previous_state: str | None = None
        silent_checks = 0
        silence_warned = False
        while True:
            await asyncio.sleep(5)
            status = await asyncio.to_thread(camilla.status)
            state = str(status.get("state") or "unreachable")
            if state != previous_state:
                logger.info(
                    "CamillaDSP state changed from %s to %s",
                    previous_state or "unknown",
                    state,
                )
                previous_state = state
            if state == "Inactive":
                logger.warning("CamillaDSP is inactive; reapplying Coldth configuration")
                applied = await asyncio.to_thread(
                    camilla.apply, store.bands(), store.balance()
                )
                logger.info("CamillaDSP configuration reapplied: %s", applied)

            transport_playing = metadata.transport().get("state") == "playing"
            signal_present = False
            if transport_playing and state == "Running":
                try:
                    levels = await asyncio.to_thread(camilla.levels)
                    capture_rms = levels.get("capture_rms") or []
                    signal_present = any(
                        math.isfinite(float(level)) and float(level) > -120
                        for level in capture_rms
                    )
                except Exception as error:
                    logger.warning("Unable to inspect capture signal: %s", error)

            if transport_playing and state == "Running" and not signal_present:
                silent_checks += 1
                if silent_checks >= 3 and not silence_warned:
                    logger.warning(
                        "AirPlay reports playing but no capture PCM has been "
                        "observed for at least 15 seconds"
                    )
                    silence_warned = True
            else:
                if silence_warned and signal_present:
                    logger.info("Capture PCM resumed")
                silent_checks = 0
                silence_warned = False

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
        initial_apply = camilla.apply(store.bands(), store.balance())
        logger.info(
            "Initial CamillaDSP configuration applied=%s rate=%s chunk=%s "
            "capture=%s playback=%s",
            initial_apply,
            settings.samplerate,
            settings.chunksize,
            settings.capture_device,
            settings.playback_device,
        )
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

    @app.middleware("http")
    async def ui_cache_policy(request, call_next):
        response = await call_next(request)
        if request.url.path in {"/", "/settings"} or request.url.path.startswith(
            "/assets/"
        ):
            response.headers["Cache-Control"] = "no-cache"
        return response

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
                "preset": store.active_preset(),
            },
            "limits": {
                "eq": {
                    "frequencies": list(BANDS),
                    "min": MIN_GAIN,
                    "max": MAX_GAIN,
                    "step": GAIN_STEP,
                },
                "balance": {
                    "min": MIN_BALANCE,
                    "max": MAX_BALANCE,
                    "step": 1,
                },
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
            {"revision": store.revision(), "bands": bands, "preset": None},
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

    async def save_preset_value(
        payload: dict[str, Any], event_type: str
    ) -> dict[str, Any]:
        try:
            preset = store.save_preset(payload)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        await events.publish(
            event_type,
            {"revision": store.revision(), "preset": preset},
        )
        return preset

    async def load_preset_value(name: str) -> tuple[dict[str, Any], bool]:
        try:
            preset = store.load_preset(name)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Preset not found") from error
        applied = await asyncio.to_thread(
            camilla.apply, preset["bands"], store.balance()
        )
        await events.publish(
            "preset.loaded",
            {
                "revision": store.revision(),
                "preset": preset,
                "tone": {
                    "bands": preset["bands"],
                    "preset": preset["name"],
                },
            },
        )
        return preset, applied

    async def delete_preset_value(name: str) -> None:
        try:
            deleted_name = store.delete_preset(name)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Preset not found") from error
        await events.publish(
            "preset.deleted",
            {"revision": store.revision(), "name": deleted_name},
        )

    @app.get("/api/v1/state")
    def get_v1_state() -> dict[str, Any]:
        return canonical_state()

    @app.get("/api/v1/health/audio")
    def get_v1_audio_health() -> dict[str, Any]:
        engine = camilla.status()
        levels: dict[str, Any] | None = None
        error: str | None = None
        try:
            levels = camilla.levels()
        except Exception as caught:
            error = str(caught)
        capture_rms = (levels or {}).get("capture_rms") or []
        playback_rms = (levels or {}).get("playback_rms") or []
        flowing = any(
            math.isfinite(float(level)) and float(level) > -120
            for level in capture_rms
        )
        return {
            "timestamp": utc_timestamp(),
            "transport": metadata.transport().get("state"),
            "engine": engine_name(engine),
            "captureRms": capture_rms,
            "playbackRms": playback_rms,
            "pcmFlowing": flowing,
            "spectrumFlowing": analyzer.levels() is not None,
            "error": error or engine.get("error") or engine.get("apply_error"),
        }

    @app.get("/api/v1/settings")
    def get_v1_settings() -> dict[str, Any]:
        return {
            "privacy": store.privacy(),
            "sources": {
                "shairportMetadata": {
                    "configured": metadata_adapter.configured,
                }
            },
        }

    @app.get("/api/v1/themes")
    def get_v1_themes() -> list[dict[str, Any]]:
        return themes.list()

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
            "tone": {"bands": bands, "preset": None},
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

    @app.get("/api/v1/presets")
    def get_v1_presets() -> list[dict[str, Any]]:
        return store.presets()

    @app.post("/api/v1/presets", status_code=201)
    async def save_v1_preset(payload: dict[str, Any]) -> dict[str, Any]:
        preset = await save_preset_value(payload, "preset.saved")
        return {"revision": store.revision(), "preset": preset}

    @app.post("/api/v1/presets/import", status_code=201)
    async def import_v1_preset(payload: dict[str, Any]) -> dict[str, Any]:
        preset = await save_preset_value(payload, "preset.imported")
        return {"revision": store.revision(), "preset": preset}

    @app.get("/api/v1/presets/{name}/export")
    def export_v1_preset(name: str) -> dict[str, Any]:
        try:
            return store.get_preset(unquote(name))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Preset not found") from error

    @app.post("/api/v1/presets/{name}/load")
    async def load_v1_preset(name: str) -> dict[str, Any]:
        preset, applied = await load_preset_value(unquote(name))
        return {
            "revision": store.revision(),
            "preset": preset,
            "tone": {"bands": preset["bands"], "preset": preset["name"]},
            "engine": camilla.status(),
            "applied": applied,
        }

    @app.delete("/api/v1/presets/{name}", status_code=204)
    async def delete_v1_preset(name: str) -> None:
        await delete_preset_value(unquote(name))

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

    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/settings", include_in_schema=False)
    def settings_page() -> FileResponse:
        return FileResponse(static_dir / "settings.html")

    return app
