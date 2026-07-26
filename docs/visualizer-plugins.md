# Future visualizer plugins

## Status

Visualizer plugins are an architectural intention, not an implemented or
supported package type.

Coldth should eventually support the exuberant, demoscene-like visualizers
associated with classic desktop audio players. They remain separate from
themes, control presentations, and DSP:

```text
Themes         declarative appearance and layout
Presentations  trusted control rendering and interaction
Visualizers    sandboxed animated rendering from measurements
DSP            private real-time audio processing
```

## Boundary

A visualizer receives normalized, read-only measurements from Coldth. It does
not connect directly to CamillaDSP, Shairport Sync, ALSA, or Coldth's command
API. It cannot change EQ, balance, volume, presets, playback, or themes.

A future frame may include:

```ts
interface VisualizerFrame {
  timestamp: number;
  leftRms: number | null;
  rightRms: number | null;
  leftPeak: number | null;
  rightPeak: number | null;
  spectrum: number[];
  waveform?: number[];
  spectralFlux?: number;
}
```

The existing ten-band analyzer remains useful for a receiver display but is
too coarse for this platform. Before visualizer plugins, Coldth should define
an optional richer measurement capability with roughly 64–128 logarithmic
spectrum bins, a 20–30 Hz update rate, and possibly a short waveform. Values
must continue to derive from real audio and must not imply more accuracy than
the analyzer provides.

## Package direction

A possible package is an ordinary archive with a manifest, executable
entrypoint, preview, documentation, and local assets:

```text
star-tunnel.coldth-visualizer
├── manifest.json
├── visualizer.js
├── preview.png
├── README.md
└── assets/
```

Visualizer identifiers use publisher-owned namespaces. The
`coldth.visualizer/*` namespace is reserved for the Coldth project.

Visualizers contain executable code and therefore use a different trust model
from `.coldth-theme` packages. Installation must require explicit approval.

## Runtime direction

The browser should perform visual rendering with Canvas, WebGL, or a similarly
bounded client API. The Pi computes and streams measurement data; it does not
render animation frames.

A minimal lifecycle is:

```ts
interface ColdthVisualizer {
  mount(canvas: HTMLCanvasElement, context: VisualizerContext): void;
  resize(width: number, height: number, pixelRatio: number): void;
  render(frame: VisualizerFrame): void;
  dispose(): void;
}
```

The runtime must isolate visualizers from the receiver application. The
eventual design should provide:

- a sandboxed iframe or worker boundary;
- no network, cookies, or persistent storage by default;
- no access to the receiver DOM outside the assigned surface;
- host-delivered measurements rather than direct API access;
- explicit capability declarations;
- frame-rate and resource limits;
- crash isolation and a reliable stop control; and
- versioned host and measurement contracts.

## Engines and presets

A visualizer engine and its visual presets are separate concepts. Coldth may
eventually support a trusted, programmable renderer whose many visual presets
are declarative data. Sharing a preset should not require installing another
executable package.

## Prerequisites

Do not implement third-party visualizers until:

1. `/api/v1/events` and measurement capabilities are stable;
2. the bundled receiver is fully migrated to v1;
3. richer spectrum data is measured and bounded on a Pi 4;
4. the sandbox and permission model are specified; and
5. one built-in test visualizer proves lifecycle and failure handling.
