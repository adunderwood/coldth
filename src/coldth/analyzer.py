from __future__ import annotations

import math
import subprocess
import threading
from collections.abc import Sequence

import numpy as np

from .model import BANDS


def analyze_pcm(
    pcm: bytes,
    samplerate: int = 44100,
    channels: int = 2,
) -> list[float] | None:
    """Reduce one S16LE PCM window to Coldth's ten display bands."""
    samples = np.frombuffer(pcm, dtype="<i2")
    if samples.size == 0 or samples.size % channels:
        return None
    frames = samples.reshape(-1, channels).astype(np.float64)
    mono = frames.mean(axis=1) / 32768.0
    if not np.any(mono):
        return [-1000.0] * len(BANDS)

    window = np.hanning(mono.size)
    spectrum = np.abs(np.fft.rfft(mono * window))
    scale = max(window.sum() / 2.0, 1.0)
    amplitudes = spectrum / scale
    frequencies = np.fft.rfftfreq(mono.size, 1.0 / samplerate)

    centers = np.asarray(BANDS, dtype=np.float64)
    boundaries = np.sqrt(centers[:-1] * centers[1:])
    lower = np.concatenate(([20.0], boundaries))
    upper = np.concatenate((boundaries, [samplerate / 2.0]))

    levels: list[float] = []
    for low, high in zip(lower, upper, strict=True):
        bins = amplitudes[(frequencies >= low) & (frequencies < high)]
        amplitude = float(np.sqrt(np.sum(np.square(bins)))) if bins.size else 0.0
        levels.append(20.0 * math.log10(max(amplitude, 1e-10)))
    return levels


class LocalSpectrumAnalyzer:
    """Optional, failure-isolated ten-band analyzer backed by ALSA arecord."""

    def __init__(
        self,
        device: str | None,
        samplerate: int = 44100,
        channels: int = 2,
        frames_per_window: int = 2048,
        command: Sequence[str] | None = None,
    ):
        self.device = device.strip() if device else ""
        self.samplerate = samplerate
        self.channels = channels
        self.frames_per_window = frames_per_window
        self.command = list(command) if command else None
        self._lock = threading.Lock()
        self._levels: list[float] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        if not self.device or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="coldth-analyzer", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process is not None:
            process.terminate()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        self._thread = None
        self._process = None
        with self._lock:
            self._levels = None

    def levels(self) -> list[float] | None:
        with self._lock:
            return self._levels.copy() if self._levels is not None else None

    def _arecord_command(self) -> list[str]:
        return self.command or [
            "arecord",
            "-q",
            "-D",
            self.device,
            "-f",
            "S16_LE",
            "-c",
            str(self.channels),
            "-r",
            str(self.samplerate),
            "-t",
            "raw",
        ]

    def _run(self) -> None:
        window_bytes = self.frames_per_window * self.channels * 2
        while not self._stop.is_set():
            try:
                self._process = subprocess.Popen(
                    self._arecord_command(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
                assert self._process.stdout is not None
                while not self._stop.is_set():
                    pcm = bytearray()
                    while len(pcm) < window_bytes and not self._stop.is_set():
                        chunk = self._process.stdout.read(window_bytes - len(pcm))
                        if not chunk:
                            break
                        pcm.extend(chunk)
                    if len(pcm) != window_bytes:
                        break
                    levels = analyze_pcm(bytes(pcm), self.samplerate, self.channels)
                    with self._lock:
                        self._levels = levels
            except (OSError, subprocess.SubprocessError):
                pass
            finally:
                if self._process is not None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait(timeout=1)
                    self._process = None
                with self._lock:
                    self._levels = None
            self._stop.wait(2)
