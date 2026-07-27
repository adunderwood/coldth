# Coldth theme packages

## Implementation status

The package-loader and first activation slice are implemented. Coldth accepts raw
`.coldth-theme` ZIP archives at `POST /api/v1/themes/install`, validates the
complete archive in a staging directory, and atomically installs it under the
persistent data directory. Installed packages appear in `GET /api/v1/themes`
and can be installed from the settings page. `GET /api/v1/themes/{id}` returns
the effective descriptor consumed by receiver clients.

Manifest, CSS, asset, semantic-token, faceplate-language, legacy layout,
component, presentation, and presentation-option validation are active.
Unsafe paths, symlinks, encrypted entries, executable formats, HTML, remote
CSS, unsafe SVG, oversized archives, unknown API or faceplate schema versions,
and reserved identifiers are rejected.

Single-parent inheritance is active. Coldth resolves parent CSS, tokens, and
layout regions into one descriptor before activation; it never installs a
theme whose parent is missing and never activates a partial inheritance chain.

The bundled receiver applies all eight v1 semantic tokens and selects the
matching `portrait` or `landscape` layout. Layout regions may choose and
configure registered built-in presentations. Components omitted from a layout
continue to use Coldth's default presentation, so a deliberately small package
remains usable.

Coldth stores one installed copy of each theme. A newer upload is fully
validated in staging and then atomically replaces the installed copy. Settings
can uninstall a theme after dependency checks. Reinstalling an older package
is the manual recovery path; Coldth does not retain a local version history.

## Boundary

A theme replaces the industrial designer. It may choose the arrangement,
materials, assets, typography, and registered presentation of each public
receiver control.

A theme does not execute code, call the API directly, define a new DSP
parameter, or implement input handling.

Executable visualizers and controls are plugins, which are a separate future
package type with a different trust model.

## Package format

A `.coldth-theme` file is a ZIP archive:

```text
braun.coldth-theme
├── manifest.json
├── faceplate.yaml
├── theme.css
├── preview.png
├── README.md
├── assets/
│   ├── fonts/
│   ├── textures/
│   └── indicators/
```

Themes contain no JavaScript and no arbitrary HTML.

## Manifest

```json
{
  "id": "com.example.braun",
  "name": "Braun",
  "version": "1.0.0",
  "apiVersion": 1,
  "author": "Example",
  "extends": "black-1987",
  "styles": "theme.css",
  "faceplate": "faceplate.yaml",
  "preview": "preview.png",
  "requires": {
    "components": ["stereo-meters", "eq", "balance", "preamp"],
    "presentations": [
      "coldth.presentation/analog-vu@1",
      "coldth.presentation/vertical-fader@1",
      "coldth.presentation/rotary-knob@1"
    ]
  }
}
```

`id`, `version`, and `apiVersion` are required. A package may have exactly one
parent. Multiple inheritance, remote dependencies, and executable install
hooks are not supported.

New themes should reference one `faceplate.yaml` document. Coldth still reads
the earlier orientation-specific JSON `layouts` form while existing packages
are migrated, but a manifest cannot declare both forms. The faceplate document
uses its own language and schema identity:

```yaml
language: coldth.faceplate
schemaVersion: "0.1"
```

The faceplate schema is independent of the theme package version, theme API
version, and Coldth application version. See
[the Coldth Faceplate Language](faceplate-language.md) for its bounded
receiver-specific vocabulary.

## Components and presentations

A component is a semantic receiver function:

```text
eq
balance
stereo-meters
spectrum
tone-bank
presets
track-info
album-art
```

A presentation is a trusted, versioned Coldth implementation of a component's
rendering and interaction:

```text
horizontal-slider
vertical-fader
rotary-knob
analog-vu
led-bar
fluorescent-spectrum
fader-ladder
```

Themes select and configure presentations. They do not implement them.

`tone-bank` is a composite of the EQ control and spectrum measurement. It lets
a trusted presentation pair each writable band with its corresponding
read-only meter while preserving the same canonical API state. For example:

```json
{
  "id": "tone-bank",
  "component": "tone-bank",
  "presentation": "coldth.presentation/fader-ladder@1",
  "options": {
    "orientation": "vertical",
    "segments": 24
  }
}
```

Themes may style and place the generated faders and ladder segments, including
their normal, warm, hot, lit, and unlit states. Themes cannot create controls,
change their bindings, or supply event-handling code.

Presentations have stable identifiers and major versions, such as
`coldth.presentation/rotary-knob@1`. Built-in presentations ship with Coldth.
A future presentation package may add trusted code, but it is installed and
approved as a plugin, never smuggled inside a theme.

### Presentation namespaces

The `coldth.presentation/*` namespace is permanently reserved for
presentations distributed by the Coldth project. The installer must reject a
third-party package that claims it.

Third-party presentations use a reverse-domain namespace controlled by their
publisher:

```text
com.example.presentation/touch-wheel@1
org.foobar.presentation/spring-knob@1
```

Presentation identifiers have three parts:

```text
publisher.presentation/name@majorVersion
```

Publisher and presentation names use lowercase ASCII letters, digits, dots,
and hyphens. The major version is a positive integer and forms part of the
public contract. Two publishers can therefore use the same presentation name
without collision, while incompatible major versions can coexist.

Each presentation publishes:

- a JSON Schema for its theme-configurable geometry and assets;
- the parameter kinds it accepts (`continuous`, `bipolar`, `discrete`, or
  `measurement`);
- the component shapes it supports (one value, a stereo pair, or a band
  collection); and
- its accessibility and interaction contract.

Coldth rejects incompatible component/presentation pairs and unknown,
misspelled, or out-of-range presentation options before activating a theme.

## Motion model

Motion has two independent parts:

1. **value geometry** — how a normalized value is drawn;
2. **input gesture** — how pointer movement changes that value.

Both are implemented by the registered presentation. A theme supplies only
schema-validated geometry and visual assets. Input gestures come from Coldth's
platform defaults and user preferences, not from the theme.

### Rotary control

```json
{
  "component": "preamp",
  "presentation": "coldth.presentation/rotary-knob@1",
  "options": {
    "startAngle": -135,
    "endAngle": 135
  }
}
```

The component maps the public preamp range to a normalized `0..1`, then maps
that value to the configured angle:

```text
angle = startAngle + normalizedValue × (endAngle - startAngle)
```

Coldth owns pointer capture, touch behavior, keyboard arrows, Home/End,
double-click-to-center, focus state, and accessibility. The theme owns the
physical sweep and appearance.

Coldth may support rotary interaction modes such as:

- `vertical` — dragging upward increases the value;
- `horizontal` — dragging right increases the value;
- `circular` — pointer angle around the knob selects the value.

The runtime chooses a sensible platform default. A user preference may
override it globally. Themes cannot change the interaction mode, drag
sensitivity, keyboard behavior, or accessibility semantics.

The built-in `rotary-knob@1` currently permits `startAngle` and `endAngle`
while rejecting an unknown option such as `rotationSpeed`. Its public styling
parts are `legend`, `knob`, `face`, `control`, and `value`. Interaction
settings belong to Coldth's client preferences schema instead.

### Linear control

```json
{
  "component": "eq",
  "presentation": "coldth.presentation/vertical-fader@1",
  "options": {
    "axis": "y",
    "direction": "reverse",
    "travel": 220,
    "handle": "assets/indicators/fader-cap.svg"
  }
}
```

Linear presentations accept schema-validated geometry such as `axis`,
`direction`, and `travel`. Coldth maps the public parameter range to position
and owns all input behavior.

### Meter movement

```json
{
  "component": "stereo-meters",
  "presentation": "coldth.presentation/analog-vu@1",
  "options": {
    "startAngle": -48,
    "endAngle": 42,
    "attackMs": 35,
    "releaseMs": 280,
    "needleOrigin": [0.5, 0.91]
  }
}
```

Meter presentations consume public dBFS measurements. Themes may tune bounded
visual ballistics, but cannot change measurement data or execute per-frame
code.

## Faceplate layout

`faceplate.yaml` describes one root frame for each responsive layout:

```yaml
language: coldth.faceplate
schemaVersion: "0.1"

layouts:
  landscape:
    root:
      frame: receiver
      direction: column
      gap: 16
      children:
        - frame: stereo
          direction: row
          gap: 32
          padding: 24
          children:
            - surface: meters
              width: fill
            - surface: balance
              width: fill

        - surface: tone
          width: fill

        - surface: presets
          width: fill
```

The frame engine creates the elements. Theme CSS styles stable faceplate,
frame, surface, state, and presentation-part selectors. Layout properties
belong to the faceplate document, not its CSS.

Coldth's stable receiver surfaces are:

```text
meters      stereo RMS and peak measurements
balance     stereo balance control
preamp      manual input gain
spectrum    ten-band spectrum measurement
track-info  title, artist, album, and transport state
album-art   current artwork
tone        EQ or composite tone-bank presentation
presets     preset controls
```

Coldth appends omitted surfaces in the safe default order, so a theme cannot
accidentally remove an interactive control. The optional `hidden` array
deliberately suppresses only observational surfaces: `meters`, `spectrum`,
`track-info`, and `album-art`. Interactive `balance`, `preamp`, `tone`, and
`presets` cannot be hidden.

Frames may nest to eight levels and contain at most 64 total nodes per layout.
Frame and surface IDs are unique within a layout. Empty frames collapse when
all optional descendants are unavailable and never change descendant state or
presentation behavior.

Themes style the root through `data-faceplate`, frames through `data-frame`,
surfaces through `data-surface`, and presentation internals through documented
`data-part` values. The header, engine status, message region, and product
signature remain application-owned.

When inheriting, a child root frame replaces its parent's root for the same
orientation while presentation regions continue to merge by ID. Omitted
orientations continue to inherit.

## Semantic tokens

Themes define receiver materials rather than application implementation
details:

```json
{
  "receiver.faceplate": "#070909",
  "receiver.panel": "#0b0d0d",
  "receiver.glass": "#030706",
  "receiver.legend": "#b58b50",
  "receiver.led": "#56f29b",
  "receiver.meter.normal": "#56f29b",
  "receiver.meter.hot": "#f1a94a",
  "receiver.accent": "#56f29b"
}
```

Coldth converts these to internal CSS variables. The token contract is
versioned with `apiVersion`.

## Inheritance

A theme may extend exactly one installed parent:

```json
{"extends": "black-1987"}
```

Resolution order is:

1. built-in fallback;
2. parent manifest, tokens, layout, and CSS;
3. child manifest, tokens, layout regions, and CSS.

Circular references and missing parents reject installation. A child replaces
a layout region by matching its `id`; it does not merge arbitrary DOM.

Parents must already be installed or bundled when the child is installed.
Effective descriptors expose `lineage` from the root parent through the
selected child and `stylesheets` in that same cascade order. Child semantic
tokens override tokens with the same name; unmentioned tokens remain
inherited.

## Package installation safety

The installer must:

- reject absolute paths and `..` traversal;
- reject symlinks;
- limit compressed file count and extracted size;
- allow only documented file types;
- reject remote CSS imports and URLs;
- validate the manifest and every layout before activation;
- extract into a temporary directory; and
- atomically move the validated version into the theme store.

A failed theme cannot partially replace the active interface. An incompatible
or missing presentation falls back to the standard built-in presentation when
the manifest marks it optional; missing required presentations reject the
theme.

## Installation API

Send the package itself as the request body:

```sh
curl --fail-with-body \
  -H 'Content-Type: application/zip' \
  --data-binary @braun.coldth-theme \
  http://coldth.local:8080/api/v1/themes/install
```

Coldth returns `201` only after complete validation and atomic installation.
An existing theme identifier accepts only a strictly newer
`major.minor.patch` version. Re-uploading an installed version or uploading an
older version returns `409`. The validated replacement becomes available from:

```text
/api/v1/themes/{id}/assets/{path}
```

Coldth retains only that active copy. Uninstall removes it but is rejected when
another installed or bundled theme depends on the target. To return to an older
release, uninstall the current package and install the older `.coldth-theme`
file. Descriptor stylesheet URLs add the active version as a cache-busting
query parameter; this does not create or retain another copy.

Package version and compatibility are separate:

- `version` orders releases of one theme package.
- `apiVersion` identifies Coldth's complete theme contract.
- Component identifiers such as `eq` remain stable for the lifetime of an API
  major version.
- Presentation identifiers carry their own major version, such as
  `coldth.presentation/fader-ladder@1`.

Coldth will not make a breaking change to a component or semantic token while
continuing to call the contract Theme API v1. A future incompatible component
model requires Theme API v2. A presentation may gain a new major identifier
alongside the old implementation, allowing themes to migrate deliberately.
This avoids both silently breaking themes and maintaining a general-purpose
dependency solver.

`extends` names a parent theme by identity, not by package-version range. A
child follows the currently installed parent release. Parent authors must
therefore treat inherited tokens, region identifiers, and assets as a public
contract within that theme's major package version. Coldth validates that the
parent exists and protects it from uninstall while children depend on it, but
does not attempt npm-style dependency resolution.

The descriptor endpoint returns the validated data used for activation:

```text
GET /api/v1/themes/{id}
```

It includes the list-entry fields plus `apiVersion`, `tokens`, and parsed
`layouts`. It never returns package paths or unvalidated manifest content.

## Architectural rule

Themes decide what the receiver looks like. Presentations decide how controls
feel. Components decide what they represent. The core decides what they do.

In shorter form: themes are data; presentations are trusted code.
