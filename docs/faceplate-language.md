# The Coldth Faceplate Language

The Coldth Faceplate Language is Coldth's declarative language for describing
the physical organization of a software stereo receiver.

It is a domain-specific language. It is not a general-purpose UI language, a
web application framework, or a mechanism for adding arbitrary behavior.

Schema `0.1` is implemented. Coldth validates YAML on the server, normalizes
it into a recursive frame tree, and sends only normalized JSON-compatible data
to receiver clients. Original Yellow and Black 1987 are authored in the
language.

## Purpose

The language exists so a faceplate can describe:

- which trusted Coldth surfaces it presents;
- how those surfaces are composed into receiver panels;
- how panels flow at supported responsive layouts;
- which Coldth presentation gives each component physical form; and
- which stable semantic elements a stylesheet may visually treat.

Its vocabulary should grow only when Coldth needs to describe a receiver
faceplate. General usefulness is not a design goal.

## Conceptual model

```text
Faceplate
└── Frame
    ├── Frame
    │   ├── Surface
    │   └── Surface
    └── Surface
        └── Component presentation
```

A faceplate is the root frame. Frames provide bounded auto-layout composition:
row or column direction, gap, padding, alignment, distribution, wrapping, and
fixed, hug-content, or fill-container sizing.

Surfaces are trusted Coldth mount points. Presentations are trusted Coldth
implementations of controls and displays. A faceplate document can select and
arrange registered capabilities; it cannot invent executable components.

The current source shape is:

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
            - surface: preamp
              width: fill

        - surface: tone
          width: fill

        - surface: presets
          width: fill
```

Frames accept:

```text
direction  row | column
gap        0..256
padding    number | [vertical, horizontal] | [top, right, bottom, left]
align      start | center | end | stretch
justify    start | center | end | space-between
wrap       true | false
width      fill | hug | 0..4096
height     fill | hug | 0..4096
```

Each frame ID and surface reference must be unique within one responsive
layout. Trees are bounded to eight levels and 64 nodes.

## Language and serialization

The language has an identity independent of its textual representation:

```yaml
language: coldth.faceplate
schemaVersion: "0.1"
```

YAML is the intended human- and AI-facing source syntax. Coldth validates and
normalizes it into JSON-compatible data before clients consume it. A future
JSON, TOML, or editor-native representation could encode the same language
without changing its semantics.

The schema version is independent of:

- the Coldth application release;
- the Coldth HTTP API version; and
- the theme package version.

An existing schema version must not silently acquire new meaning when Coldth
is released. Language evolution requires a new schema version and, once
compatibility matters, an explicit document migration.

## Ownership boundaries

```text
Faceplate document  structure, composition, spacing, alignment, and sizing
Theme CSS           color, type, material, texture, light, and ornament
Presentations       DOM, geometry, interaction, motion, and accessibility
Coldth core         canonical state, capabilities, intents, and effects
```

These boundaries keep theme authors expressive without transferring
application behavior or audio ownership into theme packages.

CSS is technically capable of changing browser layout. The supported contract
nevertheless reserves layout properties for the faceplate language. Coldth
will expose documented semantic selectors and component parts so theme CSS can
concentrate on visual treatment.

## What belongs in the language

A feature belongs when it is needed to describe the physical organization of
a Coldth receiver and cannot be expressed safely by an existing primitive.
Evidence should come from real bundled faceplates.

Likely language concerns include:

- frames and trusted surface references;
- responsive faceplate variants;
- auto-layout properties;
- presentation selection with bounded options;
- deliberate visibility of optional observational surfaces; and
- stable semantic names used by styling and authoring tools.

## What does not belong

The language does not provide:

- arbitrary HTML;
- executable JavaScript;
- network requests;
- custom application state;
- arbitrary event handlers;
- direct DSP graph manipulation;
- general-purpose data binding;
- scripting, loops, or conditionals; or
- UI primitives unrelated to Coldth receiver capabilities.

When a faceplate needs a new behavior, Coldth should first determine whether it
is a reusable semantic component or trusted presentation. The faceplate
language may then expose that registered capability declaratively.

## Authoring environments

Hand-written YAML, AI generation, and a future visual editor are equivalent
ways to author documents in the same language.

The language should ship with:

- a machine-readable schema;
- a minimal valid document;
- path-specific validation errors;
- a documented registry of surfaces and presentations;
- generated starter CSS with stable semantic hooks; and
- migration tools when a stable schema is superseded.

A visual editor should manipulate the normalized faceplate model and serialize
it without losing meaningful author intent. It should not establish a second
layout model.

Schema `0.1` is published at
[`schemas/faceplate-0.1.schema.json`](../schemas/faceplate-0.1.schema.json).
The bundled faceplates are working examples.

Generate a visual-only starter stylesheet with:

```sh
python scripts/generate-faceplate-css.py \
  src/coldth/static/themes/original-yellow/faceplate.yaml \
  /tmp/theme.css
```

The output includes stable selectors for every named frame and referenced
surface but deliberately contains no layout declarations.

## Design rule

Coldth is not trying to make its UI language generalizable.

If a proposed feature does not help describe a Coldth stereo receiver
faceplate, it does not belong in the Coldth Faceplate Language.
