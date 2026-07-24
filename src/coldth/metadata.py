from __future__ import annotations

import base64
import os
import select
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class MetadataItem:
    kind: str
    code: str
    data: bytes


def _fourcc(value: str | None) -> str:
    if not value:
        return ""
    try:
        return bytes.fromhex(value.strip()).decode("latin-1")
    except (ValueError, UnicodeDecodeError):
        return value.strip()


def parse_metadata_item(payload: bytes) -> MetadataItem:
    root = ET.fromstring(payload)
    if root.tag != "item":
        raise ValueError("Shairport metadata record must be an item")
    data_node = root.find("data")
    data = b""
    if data_node is not None and data_node.text:
        encoded = data_node.text.strip()
        if data_node.get("encoding") == "base64":
            data = base64.b64decode(encoded, validate=True)
        else:
            data = encoded.encode("utf-8")
    return MetadataItem(
        kind=_fourcc(root.findtext("type")),
        code=_fourcc(root.findtext("code")),
        data=data,
    )


class MetadataTracker:
    """Translate Shairport records into Coldth metadata and transport state."""

    CORE_FIELDS = {
        "minm": "title",
        "asar": "artist",
        "asal": "album",
    }

    def __init__(self, artwork_enabled: Callable[[], bool]) -> None:
        self._artwork_enabled = artwork_enabled
        self._lock = threading.RLock()
        self._metadata = {
            "artist": None,
            "album": None,
            "title": None,
            "artwork": None,
            "codec": None,
            "bitrate": None,
        }
        self._transport = {"state": None, "elapsed": None, "duration": None}
        self._pending: dict[str, str | None] | None = None
        self._artwork: bytes | None = None
        self._artwork_type: str | None = None

    def metadata(self) -> dict[str, str | int | None]:
        with self._lock:
            return self._metadata.copy()

    def transport(self) -> dict[str, str | float | None]:
        with self._lock:
            return self._transport.copy()

    def artwork(self) -> tuple[bytes, str] | None:
        with self._lock:
            if self._artwork is None or self._artwork_type is None:
                return None
            return self._artwork, self._artwork_type

    def clear(self) -> list[tuple[str, dict[str, object]]]:
        with self._lock:
            self._pending = None
            self._artwork = None
            self._artwork_type = None
            self._metadata.update(
                {
                    "artist": None,
                    "album": None,
                    "title": None,
                    "artwork": None,
                    "codec": None,
                    "bitrate": None,
                }
            )
            self._transport.update(
                {"state": None, "elapsed": None, "duration": None}
            )
            return [
                ("metadata.changed", self._metadata.copy()),
                ("transport.changed", self._transport.copy()),
            ]

    def clear_artwork(self) -> dict[str, object] | None:
        with self._lock:
            if self._artwork is None and self._metadata["artwork"] is None:
                return None
            self._artwork = None
            self._artwork_type = None
            self._metadata["artwork"] = None
            return self._metadata.copy()

    def consume(self, item: MetadataItem) -> list[tuple[str, dict[str, object]]]:
        with self._lock:
            if item.kind == "core" and item.code in self.CORE_FIELDS:
                field = self.CORE_FIELDS[item.code]
                value = item.data.decode("utf-8", errors="replace").strip() or None
                target = self._pending if self._pending is not None else self._metadata
                target[field] = value
                if self._pending is None:
                    return [("metadata.changed", self._metadata.copy())]
                return []

            if item.kind != "ssnc":
                return []

            if item.code == "mdst":
                self._pending = {"artist": None, "album": None, "title": None}
                return []
            if item.code == "mden" and self._pending is not None:
                self._metadata.update(self._pending)
                self._pending = None
                return [("metadata.changed", self._metadata.copy())]
            if item.code == "PICT":
                if not self._artwork_enabled() or not item.data:
                    return []
                media_type = _image_type(item.data)
                if media_type is None:
                    return []
                self._artwork = item.data
                self._artwork_type = media_type
                self._metadata["artwork"] = "/api/v1/artwork/current"
                return [("metadata.changed", self._metadata.copy())]
            if item.code in {"pbeg", "prsm"}:
                self._transport["state"] = "playing"
                return [("transport.changed", self._transport.copy())]
            if item.code == "pend":
                self._transport["state"] = "stopped"
                return [("transport.changed", self._transport.copy())]
            return []


def _image_type(payload: bytes) -> str | None:
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


class ShairportMetadataAdapter:
    """Read Shairport's XML metadata stream from a FIFO."""

    def __init__(
        self,
        pipe: str | None,
        tracker: MetadataTracker,
        callback: Callable[[str, dict[str, object]], None],
        enabled: Callable[[], bool],
    ) -> None:
        self.pipe = Path(pipe) if pipe else None
        self.tracker = tracker
        self.callback = callback
        self.enabled = enabled
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def configured(self) -> bool:
        return self.pipe is not None

    def start(self) -> None:
        if self.pipe is None or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="coldth-shairport-metadata", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        assert self.pipe is not None
        buffer = b""
        while not self._stop.is_set():
            try:
                descriptor = os.open(self.pipe, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                self._stop.wait(2)
                continue
            try:
                while not self._stop.is_set():
                    readable, _, _ = select.select([descriptor], [], [], 0.5)
                    if not readable:
                        continue
                    chunk = os.read(descriptor, 65536)
                    if not chunk:
                        self._stop.wait(0.2)
                        continue
                    buffer += chunk
                    while b"</item>" in buffer:
                        record, buffer = buffer.split(b"</item>", 1)
                        start = record.find(b"<item>")
                        if start < 0:
                            continue
                        try:
                            item = parse_metadata_item(record[start:] + b"</item>")
                        except (ValueError, ET.ParseError):
                            continue
                        if not self.enabled():
                            continue
                        for event_type, data in self.tracker.consume(item):
                            self.callback(event_type, data)
                    if len(buffer) > 16 * 1024 * 1024:
                        buffer = b""
            except OSError:
                pass
            finally:
                os.close(descriptor)
            self._stop.wait(0.5)
