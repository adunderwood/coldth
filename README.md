# Coldth

Coldth is a small, headless 10-band equalizer appliance for Raspberry Pi. It
sits between Shairport Sync and the Pi's audio output and gives you the part
that should have been simple all along: the EQ.

The project is an early but working MVP. The base AirPlay → EQ → Pi headphone
path and live stereo meters have been exercised on a dedicated Raspberry Pi 4.
The ten-band analyzer is installed by default and remains failure-isolated from
the speaker path.

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
python3 -m venv venv
. venv/bin/activate
pip install -e ".[dev]"
coldth
```

Open <http://127.0.0.1:8080>. CamillaDSP is optional during UI development;
the status indicator will show that the audio engine is offline.

Run the tests with:

```sh
pytest
npm run test:js
```

## Configuration

Environment variables:

- `COLDTH_DATA_DIR` — persistent state directory (default: `./data`)
- `COLDTH_HOST` — web bind address (default: `0.0.0.0`)
- `COLDTH_PORT` — web port (default: `8080`)
- `COLDTH_CAMILLADSP_URL` — engine socket (default: `ws://127.0.0.1:1234`)
- `COLDTH_SHAIRPORT_METADATA_PIPE` — optional Shairport Sync metadata FIFO,
  normally `/tmp/shairport-sync-metadata`
- `COLDTH_ANALYZER_DEVICE` — optional ALSA capture device for the local
  ten-band FFT, such as `hw:Loopback,1,1` (disabled when unset)
- `COLDTH_CAPTURE_DEVICE` — CamillaDSP ALSA capture device
- `COLDTH_PLAYBACK_DEVICE` — CamillaDSP ALSA playback device
- `COLDTH_CAPTURE_FORMAT` — ALSA capture sample format (default: `S16LE`)
- `COLDTH_PLAYBACK_FORMAT` — ALSA playback sample format (default: `S16LE`,
  compatible with the Pi 4 headphone device)
- `COLDTH_SAMPLE_RATE` — CamillaDSP, loopback capture, and analyzer rate
  (default: `44100`; use `48000` for a fixed-48-kHz USB DAC)
- `COLDTH_CHUNKSIZE` — CamillaDSP processing chunk size (default: `1024`;
  `2048` is a conservative USB-DAC setting)

For installation, start with the complete
[Raspberry Pi 4 guide](docs/pi4-installation.md). See
[audio architecture](docs/audio-architecture.md) for design decisions and the
[ten-band analyzer](docs/analyzer.md) using an ALSA
fan-out setup.

The current development contract lives in the v1 namespace and is documented
in [Coldth API v1](docs/api-v1.md). It remains unstable until Coldth explicitly
declares it frozen. It treats the bundled web receiver as one client of
canonical receiver state and deliberately keeps DSP topology private.
The declarative `.coldth-theme` package, layout, inheritance, and control
motion model are defined in [theme packages](docs/theme-packages.md).
Current implementation order is tracked in the
[receiver flexibility roadmap](docs/roadmap.md); the completed architectural
sequence is preserved in the
[foundation roadmap](docs/roadmap-foundation.md). The future sandboxed
visualization platform is described in
[visualizer plugins](docs/visualizer-plugins.md).
The current trusted browser control contract is documented in
[component and presentation registry](docs/component-presentations.md).
The hierarchy from faceplate through component presentation, and the behavior
loop from interaction through audio effect and feedback, are documented in the
[receiver model](docs/receiver-model.md).
The planned declarative receiver language, its ownership boundaries, and its
deliberately narrow scope are defined in
[the Coldth Faceplate Language](docs/faceplate-language.md).
Declarative `.coldth-theme` ZIP packages can be installed from `/settings`;
the package safety and compatibility contract is documented in
[theme packages](docs/theme-packages.md).

On a newly imaged Pi, the preferred installation is:

```sh
./scripts/install-pi.sh
```

The installer enables the ten-band analyzer by default. Use
`--without-analyzer` only to omit it for troubleshooting or a deliberately
minimal installation.
It also installs nginx on port 80 and keeps the Coldth application server
private on `127.0.0.1:8080`, so the receiver opens at `http://coldth.local`
without a port number.
Interactive installation also asks whether Shairport should request album
artwork. For unattended installation, choose explicitly with `--with-artwork`
or `--without-artwork`; the unattended default is off.
The installer is safe to re-run, backs up displaced system configuration, and
finishes with a service health check. A single attached USB Audio DAC is
selected automatically with conservative 48 kHz settings; explicit environment
variables remain available for ambiguous or unusual hardware. See
`./scripts/install-pi.sh --help`.

Update an existing Pi checkout and its installed Python package with:

```sh
./scripts/update-pi.sh
```

Use `--no-pull` after making or pulling changes yourself.

## Faceplates and meters

Coldth includes two faceplates: **Original Yellow** and **Black 1987**. The
selection is saved in the browser. Faceplates are declarative packages under
`src/coldth/static/themes`; each directory contains a `theme.json` manifest,
a `faceplate.yaml` Coldth Faceplate Language document, and a `theme.css`
stylesheet. They cannot add scripts or change the audio configuration.

The stereo meters use live playback RMS and peak levels from CamillaDSP. The
matching ten-band illumination is optional: Coldth reads a second ALSA
Loopback feed and reduces real PCM samples to ten inexpensive FFT buckets. If
that feed is absent, the UI says “standby” and the working audio path is
unchanged. No synthetic meter data is shown.

The stereo balance control is stored separately from EQ presets. Center leaves
both channels untouched; moving toward one side progressively attenuates the
opposite channel, reaching effective silence at full travel.

The preamp is also persistent receiver state rather than part of a preset. It
defaults to neutral `0 dB`; EQ faders apply their displayed gains literally
and never change that value automatically. Analyzer ladders include the
preamp and EQ response, with fixed hot zones serving as overload warnings.
Coldth reports excessive settings rather than silently normalizing or
limiting them.

When the Shairport metadata adapter is configured, the receiver shows the
artist, album, title, and playback state supplied by the AirPlay sender.
Privacy controls live at `/settings`. Album artwork is opt-in at both the
Shairport service and Coldth UI levels and is kept only in memory.
