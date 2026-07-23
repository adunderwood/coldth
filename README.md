# Coldth

Coldth is a small, headless 10-band equalizer appliance for Raspberry Pi. It
sits between Shairport Sync and the Pi's audio output and gives you the part
that should have been simple all along: the EQ.

The project is currently an early MVP. The browser control plane is usable on
a development machine; Raspberry Pi audio installation is the next hardware
milestone.

## Architecture

```text
Apple Music → Shairport Sync → ALSA loopback → CamillaDSP → headphone jack
                                      ↑
                              Coldth web service
```

Coldth does not implement AirPlay or real-time DSP. Shairport Sync receives the
stream and CamillaDSP performs the audio processing. Coldth owns the human
interface, settings, presets, and the intentionally narrow CamillaDSP
configuration.

## Run the development UI

Python 3.11 or newer is recommended.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
coldth
```

Open <http://127.0.0.1:8080>. CamillaDSP is optional during UI development;
the status indicator will show that the audio engine is offline.

Run the tests with:

```sh
pytest
```

## Configuration

Environment variables:

- `COLDTH_DATA_DIR` — persistent state directory (default: `./data`)
- `COLDTH_HOST` — web bind address (default: `0.0.0.0`)
- `COLDTH_PORT` — web port (default: `8080`)
- `COLDTH_CAMILLADSP_URL` — engine socket (default: `ws://127.0.0.1:1234`)
- `COLDTH_CAPTURE_DEVICE` — CamillaDSP ALSA capture device
- `COLDTH_PLAYBACK_DEVICE` — CamillaDSP ALSA playback device

See [docs/audio-architecture.md](docs/audio-architecture.md) for the Pi-specific
audio path and current assumptions.
