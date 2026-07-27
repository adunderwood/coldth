# Coldth receiver model

Coldth has two related architectural hierarchies:

1. a **physical structure** describing where receiver elements live; and
2. a **behavior loop** describing how input becomes an audible effect and
   returns as feedback.

They cooperate, but they are not the same tree. Visual containment must not
own DSP state, and canonical state must not know about visual nesting.

API v1 remains unstable during development. This document records the current
working vocabulary, not a frozen compatibility promise.

The planned declarative representation of this physical hierarchy is defined
by [the Coldth Faceplate Language](faceplate-language.md). That language is
specific to Coldth receiver faceplates and is deliberately not a
general-purpose UI language.

## Physical structure

```text
Application shell
└── Receiver faceplate
    └── Root frame
        ├── Frame
        │   ├── Surface
        │   │   └── Component presentation
        │   └── Surface
        │       └── Component presentation
        └── Surface
            └── Component presentation
```

### Application shell

The shell owns application concerns outside the themed receiver:

- navigation and Settings;
- engine status;
- API and event-stream coordination;
- error and progress messages; and
- safe fallback behavior.

Themes do not replace the shell.

### Receiver faceplate

A faceplate is the complete industrial design selected by the listener. It
coordinates:

- one or more orientation-specific layouts;
- global materials and typography;
- frame chassis;
- component faces; and
- presentation choices.

Original Yellow, Black 1987, and 1969 are receiver faceplates.

### Layout

A layout supplies one recursive root frame for an orientation or viewport. It
controls auto-layout composition and deliberate visibility of optional
displays.

Coldth appends omitted surfaces in a safe fallback position. Layouts explicitly
hide optional observational surfaces when that is the design intent.

### Frame

A frame composes child frames and independent sibling surfaces. It owns:

- background and border;
- padding and gap;
- row or column auto-layout;
- alignment, distribution, wrapping, and sizing; and
- a stable theme region.

For example:

```text
stereo
├── meters
└── balance

now-playing
├── album-art
└── track-info
```

Framing does not transfer state ownership. Album artwork does not own track
information, and meters do not own balance. Frames are layout primitives, not
new semantic components.

### Surface

A surface is an application-owned mount point for one semantic component.
Current surfaces are:

```text
meters
balance
spectrum
track-info
album-art
tone
presets
```

A surface gives layouts a stable placement target without exposing
presentation-internal DOM.

### Component

A component defines what a receiver function means:

- its canonical value shape;
- its capabilities and limits;
- the intents it accepts; and
- the state or measurements it consumes.

A component has no inherent appearance or physical location.

For example:

```text
EQ component
├── value: ten band gains
├── limits: −12 dB to +12 dB
├── intent: set band gains
└── presentations
    ├── vertical faders
    ├── horizontal faders
    └── rotary knob bank
```

### Presentation

A presentation is Coldth-owned trusted browser code that gives a component
physical form and behavior. It owns:

- generated DOM;
- value geometry;
- pointer, touch, and keyboard interaction;
- focus and accessibility behavior;
- display motion; and
- a bounded, validated options contract.

“Presentation” includes both interactive controls and passive displays.
Meters, artwork, and marquees are presentations even though the listener does
not manipulate them.

### Component face

A component face is the scoped visual treatment applied to a presentation. It
owns materials and assets, not functionality.

```text
Black 1987 meter face
├── dark segment wells
├── fluorescent fills
└── amber peak markers
```

Component faces are a working design concept. Their distributable package
contract remains deferred until the three bundled faceplates reveal stable
styling boundaries.

## Behavior loop

```text
Input
→ Interaction
→ Intent
→ Canonical state
→ Effect
→ Measurement
→ Feedback
```

### Input

Raw browser or hardware input, such as a pointer drag, touch gesture, keyboard
press, or future physical control event.

### Interaction

The presentation translates input geometry into a normalized component value.
Coldth owns interaction behavior so themes cannot compromise usability or
accessibility.

### Intent

An intent expresses what the listener means in product vocabulary:

```text
Set 125 Hz to −3 dB
Set balance to L 20
Load preset “Night”
```

Intents do not expose CamillaDSP filters, coefficients, mixers, or pipeline
topology.

### Canonical state

Coldth validates the intent and updates the shared receiver state observed by
every client and presentation.

### Effect

Coldth translates canonical state into the narrow CamillaDSP configuration
required to affect the audio signal. CamillaDSP executes the audio effect but
remains behind Coldth's product boundary.

The component says:

```text
Set 125 Hz to −3 dB
```

It never says:

```text
Rewrite biquad filter 4
```

### Measurement

CamillaDSP and the optional analyzer report ephemeral observations such as:

- stereo RMS;
- stereo peak;
- ten-band spectrum levels; and
- engine health.

Measurements are not invented when unavailable.

### Feedback

The event stream returns canonical state changes and normalized measurements
to every mounted presentation. Controls, meters, and displays render the same
shared truth.

## Complete model

```text
                            RECEIVER STRUCTURE

Application shell
└── Faceplate
    └── Layout
        └── Surface group
            └── Surface
                └── Component presentation
                         │
                         │ produces intent / consumes state
                         ▼
                         BEHAVIOR LOOP

Input → Interaction → Intent → Canonical state → Effect
                                  ▲                 │
                                  └── Feedback ← Measurement
```

The styling hierarchy runs alongside the physical structure:

```text
Receiver faceplate
├── Global materials
├── Surface-group chassis
└── Component face
    └── Presentation parts
```

This separation lets Coldth rearrange and restyle a receiver freely without
changing what its controls mean or how audio state is applied.
