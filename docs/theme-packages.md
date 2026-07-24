# Coldth theme packages

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
├── theme.css
├── preview.png
├── README.md
├── assets/
│   ├── fonts/
│   ├── textures/
│   └── indicators/
└── layouts/
    ├── landscape.json
    └── portrait.json
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
  "extends": "coldth.receiver-base",
  "styles": "theme.css",
  "preview": "preview.png",
  "layouts": {
    "landscape": "layouts/landscape.json",
    "portrait": "layouts/portrait.json"
  },
  "requires": {
    "components": ["stereo-meters", "eq", "balance"],
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

## Components and presentations

A component is a semantic receiver function:

```text
eq
balance
stereo-meters
spectrum
presets
metadata
transport
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
```

Themes select and configure presentations. They do not implement them.

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
  "component": "balance",
  "presentation": "coldth.presentation/rotary-knob@1",
  "options": {
    "startAngle": -135,
    "endAngle": 135,
    "indicator": "assets/indicators/white-line.svg",
    "size": 92
  }
}
```

The component maps the public balance range `-100..100` to a normalized
`0..1`, then maps that value to the configured angle:

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

For example, the built-in `rotary-knob@1` option schema can permit
`startAngle`, `endAngle`, `indicator`, and `size`, while rejecting an unknown
option such as `rotationSpeed`. Interaction settings belong to Coldth's client
preferences schema instead.

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

## Layout

Layouts arrange components in named regions:

```json
{
  "regions": [
    {
      "id": "meters",
      "component": "stereo-meters",
      "presentation": "coldth.presentation/analog-vu@1",
      "options": {
        "startAngle": -48,
        "endAngle": 42
      }
    },
    {
      "id": "tone",
      "component": "eq",
      "presentation": "coldth.presentation/vertical-fader@1"
    },
    {
      "id": "balance",
      "component": "balance",
      "presentation": "coldth.presentation/rotary-knob@1",
      "options": {
        "startAngle": -135,
        "endAngle": 135
      }
    }
  ]
}
```

The layout engine creates the elements. Theme CSS styles stable component,
region, state, and part selectors.

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
{"extends": "coldth.receiver-base"}
```

Resolution order is:

1. built-in fallback;
2. parent manifest, tokens, layout, and CSS;
3. child manifest, tokens, layout regions, and CSS.

Circular references and missing parents reject installation. A child replaces
a layout region by matching its `id`; it does not merge arbitrary DOM.

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

## Architectural rule

Themes decide what the receiver looks like. Presentations decide how controls
feel. Components decide what they represent. The core decides what they do.

In shorter form: themes are data; presentations are trusted code.
