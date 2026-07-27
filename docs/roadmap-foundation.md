# Coldth foundation roadmap — completed

This roadmap records the completed foundation sequence. It is retained as a
historical description of why Coldth's API, component registry, and
declarative theme boundary exist.

During active development, API v1 remains unstable. The project may revise the
contract without compatibility layers until v1 is explicitly declared stable.

## Completed sequence

### 1. Unified v1 event stream — implemented

`WS /api/v1/events` currently carries:

- a canonical `state.snapshot` on connection;
- `tone.changed` events;
- normalized `meter.frame` events;
- `metadata.changed` events;
- `transport.changed` events; and
- `settings.changed` events.

### 2. Move presets under v1 — implemented

Versioned preset list, save, import, export, load, and delete operations are
implemented. They publish `preset.saved`, `preset.imported`, `preset.loaded`,
and `preset.deleted`. The built-in `Flat` preset remains immutable.

The active preset is canonical, persistent state. Loading a preset sets it;
manual EQ changes and deletion or replacement of the active preset clear it.

### 3. Migrate the bundled receiver to v1 — implemented

The bundled receiver uses v1 for canonical state, EQ, balance, themes,
presets, meters, metadata, transport, and settings. Reset loads the built-in
`Flat` preset rather than calling a special endpoint.

The prototype's unversioned endpoints were removed before Coldth's first
public API contract. There is no compatibility surface to maintain.

### 4. Introduce the built-in component/presentation registry — implemented

Represent semantic components such as EQ, balance, meters, metadata, and
presets independently from trusted presentations such as faders, rotary
controls, LED ladders, and analog meters.

The dependency-free registry, option validation, and lifecycle contract are
implemented. EQ, balance, stereo meters, spectrum, metadata, and presets all
render through bundled presentations while the app shell coordinates the v1
API and event stream.

Prove the complete registry using Coldth's bundled receiver before exposing
package installation. See
[component and presentation registry](component-presentations.md).

### 5. Validate and load declarative theme packages — implemented

Implement `.coldth-theme` ZIP validation, safe extraction, manifests,
single-parent inheritance, semantic tokens, layouts, presentation option
schemas, compatibility checks, and atomic activation.

Themes remain data and contain no JavaScript or arbitrary HTML.

The secure ZIP loader, persistent theme store, manifest and layout validation,
built-in presentation compatibility checks, constrained asset serving,
atomic first install, API endpoints, settings-page installer, semantic-token
application, orientation-aware layout selection, presentation options, and
component-level fallback are implemented. Single-parent inheritance now
resolves CSS, semantic tokens, and matching layout region IDs together, with
missing-parent and cycle rejection. Themes can physically reorder the stable
levels, tone, and presets receiver surfaces, with safe fallback for omitted
surfaces. Single-copy atomic updates, semantic-version ordering,
dependency-safe uninstall, management API events, and settings-page controls
are implemented. Package versions order theme releases; Theme API majors and
versioned presentation identifiers define compatibility.

The first composite presentation is also implemented: Black 1987 uses the
landscape `fader-ladder@1` tone bank to pair every EQ band with a discrete,
theme-styleable spectrum ladder. Portrait retains the established horizontal
phone controls.

## Explicitly outside the foundation

### Third-party presentation plugins — intentionally deferred

Presentations are trusted executable code. Do not open third-party
installation until the built-in component and presentation contracts have
survived real use and versioning.

## Work completed alongside the sequence

- Persistent balance control
- Live stereo meters
- Optional honest ten-band spectrum approximation
- Shairport metadata adapter
- Now-playing title, artist, album, and playback state
- Opt-in, memory-only album artwork
- Browser privacy settings
- Raspberry Pi installer and verification tooling
- Ordered audio-stack restart and diagnostic bundle tooling
- Persistent journald engine logs and silent-playback observability

### Future visualizer platform

Visualizer plugins are a deliberate future direction, but are not part of the
current implementation sequence. See
[visualizer plugins](visualizer-plugins.md).

They should begin only after the canonical event and measurement contracts are
stable enough to support a richer spectrum without coupling plugins to
CamillaDSP or ALSA.
