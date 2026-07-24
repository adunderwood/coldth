# Coldth API v1

## Implementation status

The first v1 slice is implemented:

```text
GET /api/v1/state
GET /api/v1/settings
PUT /api/v1/settings/privacy
GET /api/v1/artwork/current
PUT /api/v1/tone/eq
PUT /api/v1/tone/balance
WS  /api/v1/events
```

The existing unversioned endpoints remain available for the bundled UI and
delegate to the same store and CamillaDSP application path. The event stream
sends an initial canonical snapshot, `tone.changed` events, and normalized
`meter.frame`, `metadata.changed`, and `transport.changed` events. Shairport
metadata, privacy settings, and current in-memory artwork are implemented.
Preset routes and their events are the next migration slice; they are not
implemented under `/api/v1` yet.

## Purpose

Coldth's API is the product boundary. The bundled receiver faceplate is one
client. A phone UI, hardware control panel, alternate faceplate, or
visualization should observe and manipulate the same canonical receiver state.

The public vocabulary describes what a listener can understand:

- equalizer bands;
- stereo balance;
- volume, when Coldth owns it;
- presets;
- audio-engine health;
- transport and track metadata, when a source provides them; and
- measurements.

It does not expose CamillaDSP filters, coefficients, mixers, pipelines, Q
values, or ALSA topology.

## Design rules

1. The API is versioned under `/api/v1`.
2. State reads are boring JSON.
3. Mutations are validated commands with explicit results.
4. One WebSocket carries snapshots, changes, metadata, and meter frames.
5. Every optional datum has a capability flag.
6. Missing information is `null` or unsupported, never guessed.
7. Themes contain declarative semantic tokens and layouts, never executable
   server code.
8. High-rate measurements are ephemeral and are not written to persistent
   state.

## Canonical state

`GET /api/v1/state`

```json
{
  "revision": 42,
  "timestamp": "2026-07-23T21:15:30.123Z",
  "capabilities": {
    "eq": true,
    "balance": true,
    "volume": false,
    "presets": true,
    "stereoMeters": true,
    "spectrum": true,
    "transport": false,
    "metadata": false
  },
  "tone": {
    "bands": {
      "31": 0.0,
      "62": -2.0,
      "125": -3.0,
      "250": -2.0,
      "500": 0.0,
      "1000": 0.0,
      "2000": 0.0,
      "4000": 0.0,
      "8000": 0.0,
      "16000": 0.0
    },
    "balance": 0,
    "preset": null
  },
  "audio": {
    "engine": "running",
    "sampleRate": 44100,
    "bitDepth": 16,
    "channels": 2,
    "input": "airplay",
    "volume": null
  },
  "transport": {
    "state": null,
    "elapsed": null,
    "duration": null
  },
  "metadata": {
    "artist": null,
    "album": null,
    "title": null,
    "artwork": null,
    "codec": null,
    "bitrate": null
  }
}
```

### Why capabilities are part of state

Coldth must work in degraded configurations. Stereo meters may be live while
the FFT is unavailable. Shairport may deliver audio without metadata. A client
should render only controls and displays backed by real functionality.

### Revisions

`revision` increases whenever persistent or observable low-rate state changes.
Clients can ignore duplicate events and can request a fresh snapshot after a
connection loss. Meter frames do not increment it.

## Commands

Commands accept intent and return the updated canonical fragment plus engine
application status.

### Equalizer

`PUT /api/v1/tone/eq`

```json
{
  "bands": {
    "31": 0,
    "62": -2,
    "125": -3,
    "250": -2,
    "500": 0,
    "1000": 0,
    "2000": 0,
    "4000": 0,
    "8000": 0,
    "16000": 0
  }
}
```

### Balance

`PUT /api/v1/tone/balance`

```json
{"balance": -20}
```

Balance ranges from `-100` (left) through `0` (center) to `100` (right).

### Presets

```text
GET    /api/v1/presets
POST   /api/v1/presets
DELETE /api/v1/presets/{name}
POST   /api/v1/presets/{name}/load
GET    /api/v1/presets/{name}/export
POST   /api/v1/presets/import
```

The built-in `Flat` preset resets EQ bands. Balance is receiver state and is
not part of an EQ preset.

### Volume

Volume is not writable in v1 until Coldth owns a single, predictable gain
stage. AirPlay source volume and CamillaDSP global gain must not appear as two
uncoordinated controls. Until that is resolved:

```json
{"volume": null}
```

and `capabilities.volume` is `false`.

### Transport

Transport is initially observational. Play, pause, seek, next, and previous are
not advertised unless the active input supplies reliable commands.

## Measurements

Measurements use a normalized frame shared by every visualization:

```json
{
  "leftRms": -24.3,
  "rightRms": -25.1,
  "leftPeak": -8.7,
  "rightPeak": -9.2,
  "spectrum": [-42.0, -35.2, -28.1, -31.0, -36.4, -39.0, -41.2, -44.5, -48.0, -52.1],
  "timestamp": "2026-07-23T21:15:30.123Z"
}
```

Levels are dBFS. `spectrum` is either ten values in Coldth band order or
`null`. This frame is not a promise of laboratory accuracy; it is a promise
that values derive from real audio.

## Event stream

`WS /api/v1/events`

The server sends a full snapshot immediately after connection:

```json
{
  "seq": 100,
  "type": "state.snapshot",
  "timestamp": "2026-07-23T21:15:30.000Z",
  "data": {}
}
```

Subsequent envelopes use the same shape:

```json
{
  "seq": 101,
  "type": "tone.changed",
  "timestamp": "2026-07-23T21:15:30.050Z",
  "data": {"balance": -20}
}
```

Initial event types:

```text
state.snapshot
tone.changed
preset.loaded
audio.changed
transport.changed
metadata.changed
meter.frame
theme.changed
error
```

`seq` orders events within one server process. Clients reconnect and consume a
new snapshot rather than requesting replay in v1.

Meter frames may be dropped or coalesced for a slow client. State events may
not be silently dropped.

## Metadata

Metadata fields are nullable:

```json
{
  "artist": "Artist",
  "album": "Album",
  "title": "Track",
  "artwork": "/api/v1/artwork/current",
  "codec": "ALAC",
  "bitrate": 1411200
}
```

Coldth publishes only values received from the active input adapter. Metadata
collection is an adapter concern; canonical state does not know Shairport's
pipe, socket, or process details.

Artwork is served through a same-origin Coldth endpoint. Themes do not receive
filesystem paths or arbitrary remote URLs.

## Themes

`GET /api/v1/themes`

The complete package and motion contract is defined in
[theme-packages.md](theme-packages.md).

A theme manifest uses semantic receiver tokens:

```json
{
  "id": "black-1987",
  "name": "Black 1987",
  "version": 1,
  "tokens": {
    "receiver.faceplate": "#070909",
    "receiver.panel": "#0b0d0d",
    "receiver.glass": "#030706",
    "receiver.legend": "#b58b50",
    "receiver.led": "#56f29b",
    "receiver.meter.normal": "#56f29b",
    "receiver.meter.hot": "#f1a94a",
    "receiver.accent": "#56f29b"
  },
  "controls": {
    "eq": "vertical-fader",
    "balance": "horizontal-slider",
    "volume": "rotary-knob"
  }
}
```

The exact token list is a versioned contract. CSS variables are an
implementation detail generated from tokens.

Themes may choose registered control presentations, but cannot provide
JavaScript. A theme that requests an unknown presentation falls back to the
standard control.

## Client control bindings

`ColdthControl` is a client-side interface, not a network endpoint:

```ts
interface ColdthControl<T> {
  mount(element: HTMLElement): void
  setValue(value: T): void
  setEnabled(enabled: boolean): void
  onIntent(handler: (value: T) => void): void
  destroy(): void
}
```

A binding maps a registered presentation to one public parameter:

```json
{
  "parameter": "tone.balance",
  "presentation": "horizontal-slider"
}
```

The control emits listener intent. The API validates it, updates canonical
state, applies it to the engine, and broadcasts the resulting state. Controls
never manipulate DSP directly.

## Internal boundaries

The implementation should separate:

```text
Input adapters ─┐
DSP adapter ────┼→ Coldth Core → HTTP commands
Analyzer ───────┤             ↘ WebSocket events
State store ────┘
```

- **Core** owns canonical receiver state, validation, revisions, and events.
- **DSP adapter** translates listener intent into CamillaDSP configuration.
- **Input adapter** translates Shairport or future sources into transport and
  metadata observations.
- **Analyzer** produces ephemeral meter frames.
- **HTTP/WebSocket layer** serializes the public contract.

FastAPI route handlers should not become the canonical state model.

## Migration from the MVP API

The existing unversioned endpoints remain temporarily:

```text
/api/state
/api/eq
/api/balance
/api/presets
/api/meters
/api/themes
```

Implementation sequence:

1. introduce core state and event types behind existing routes;
2. make the current UI consume `/api/v1/state` and `/api/v1/events`;
3. add compatibility wrappers for old routes;
4. move theme manifests to semantic tokens;
5. add input metadata adapters; and
6. remove unversioned endpoints only in a future major release.

This sequence changes the inside before replacing the working faceplate.
