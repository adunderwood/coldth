# Coldth receiver flexibility roadmap

The foundation roadmap is complete and preserved in
[foundation roadmap](roadmap-foundation.md). This active roadmap uses three
distinct bundled faceplates to pressure-test Coldth's component and theme
contracts before third-party executable plugins are considered.

This is an implementation order, not a release schedule. API v1 remains
unstable during development: bundled themes and clients move with the current
contract, and Coldth will not add compatibility layers until v1 is explicitly
declared stable.

## Design target

Coldth should ship three faceplates with genuinely different physical models:

| Faceplate | Tone controls | Measurements | Track display |
| --- | --- | --- | --- |
| Original Yellow | Clean touch-friendly controls | Minimal modern meters | Contemporary, artwork-forward |
| Black 1987 | Plain graphic faders | Standalone fluorescent spectrum | LED marquee |
| 1969 | Rotary knob bank | Analog VU needles | Minimal or absent |

These names establish a design direction, not a historical reproduction
standard. **1969** means older, sparse, tactile hi-fi rather than a claim that
every material or control existed in that exact year. If the completed design
belongs more naturally to 1972 or 1979, Coldth can rename it. The goal is to
paint an era, not reproduce one artifact.

Original Yellow represents the present day: clean, touch-friendly,
artwork-forward, and influenced by contemporary streaming interfaces while
remaining unmistakably Coldth. It should not carry the visual obligations of
2004-era software.

Themes arrange and style Coldth-owned semantic components. They do not add
controls, fetch data, process audio, or execute JavaScript.

The working mental model has four layers:

```text
semantic component → presentation → component face → receiver layout
```

A component owns meaning and state. A presentation owns structure,
interaction, and motion. A component face owns the scoped visual treatment and
assets for that presentation. A receiver faceplate coordinates component
faces, layout, and global materials into a complete design.

Implementation friction is recorded in the
[theme pain diary](theme-pain-diary.md). Repeated evidence across faceplates,
not speculative elegance, should drive the eventual refactor.

## Implementation sequence

### 1. Granular receiver surfaces — implemented

Replace the compound `levels` layout surface with independently placeable
surfaces:

```text
meters
balance
spectrum
track-info
album-art
tone
presets
```

The application shell continues to create every surface and append omitted
surfaces in a safe default order. Omission therefore means “use the fallback,”
not “hide this.” Layouts gain a validated visibility field for deliberately
suppressing optional observational surfaces such as meters, spectrum,
track information, or artwork. Interactive receiver controls remain available.

Completion means:

- L/R meters can be placed without metadata or spectrum;
- track information and artwork can be placed without L/R meters;
- spectrum can be placed independently from EQ controls;
- optional displays can be deliberately hidden without CSS tricks;
- existing bundled themes retain sensible layouts through fallback; and
- portrait and landscape layouts can order the granular surfaces separately.

The shell, validation contract, fallback order, explicit optional visibility,
and bundled-theme migration are implemented. The existing spectrum overlay
still reaches into EQ presentation DOM; the standalone spectrum work in step
4 removes that remaining coupling.

### 2. Split track information and album artwork — implemented

Replace the combined metadata presentation with two semantic components that
observe the same canonical metadata state:

- `track-info` — title, artist, album, and transport state;
- `album-art` — artwork availability and same-origin artwork URL.

Provide conventional built-in presentations for both. Absence of metadata or
artwork must collapse cleanly without leaving an empty decorative panel.

Both components now mount and advertise availability independently while
observing the same canonical metadata and transport state.

### 3. Declarative surface groups — implemented

Test a layout-level grouping model for components that remain semantically
independent but sometimes share one visual chassis:

```text
stereo       meters + balance
now-playing  album-art + track-info
```

A group should own shared panel chrome, padding, and member arrangement. Its
members remain ordinary Coldth components with independent state,
presentations, availability, and optional visibility.

Start with named, flat groups rather than arbitrary recursive nesting.
Portrait and landscape layouts may arrange the same members differently or
omit the group and place them independently. The exact manifest shape remains
unstable until Original Yellow and Black 1987 both exercise it.

Completion means:

- grouped surfaces share one background, border, padding model, and theme
  region;
- a group can arrange members in a row or column without component-specific
  code;
- unavailable optional members collapse without leaving a broken chassis;
- the same surface belongs to at most one group in a layout;
- ungrouped surfaces retain safe fallback placement; and
- grouping does not change component state ownership or presentation
  behavior.

Flat groups, group-aware flow, row/column direction, single-group membership,
empty-group collapse, safe fallback, inheritance, and bundled landscape and
portrait layouts are implemented. Original Yellow and Black 1987 both use
`stereo` and `now-playing` chassis.

### 3a. Generalize surface groups into auto-layout frames — implemented

Treat the faceplate as a root frame and surface groups as nested frames rather
than adding more one-off container types. Borrow the small, useful subset of
Figma auto layout:

- recursive frames containing frames or trusted surface references;
- row or column direction;
- gap and padding;
- start, center, end, and space-between distribution;
- start, center, end, and stretch alignment;
- optional wrapping; and
- fixed, hug-content, and fill-container sizing.

Controls remain trusted leaves. Theme packages may arrange and style them but
may not supply executable controls or arbitrary application markup. Keep the
layout vocabulary declarative and bounded; absolute positioning, constraints,
and freeform transforms are intentionally outside the first contract.

This supersedes the flat `groups` shape once the recursive contract is proven.
During the unstable v1 period, bundled themes can migrate directly without a
legacy compatibility layer.

Schema `coldth.faceplate` `0.1`, YAML loading, bounded recursive frame
validation, normalized descriptors, browser rendering, semantic frame,
surface, and presentation-part hooks, bundled-theme migration, the
machine-readable schema, and visual-only starter CSS generation are
implemented.

#### Faceplate authoring contract

The architectural boundary and vocabulary are defined in
[the Coldth Faceplate Language](faceplate-language.md).

Use a declarative YAML file as the human- and AI-facing authoring format for
the frame tree. Coldth validates it and normalizes it to JSON-compatible data
before exposing it to the browser. YAML is an authoring convenience, not a
second runtime state model.

Treat the document as an instance of the Coldth faceplate language, not as
“some YAML.” Every faceplate declares that language and its schema version:

```yaml
language: coldth.faceplate
schemaVersion: "0.1"
```

`schemaVersion` versions the meaning and structure of the faceplate document.
It is independent of the Coldth application release, the theme package
version, and the HTTP API version. Use a string rather than a YAML number so
versions remain identifiers instead of acquiring numeric comparison semantics.

The language also remains independent of its serialization. A future JSON,
TOML, editor-native, or other representation can encode the same normalized
faceplate model without defining a new layout language. Coldth may advertise
which faceplate schema versions it accepts, but application releases do not
implicitly redefine an existing schema version.

Keep layout and appearance deliberately separate:

```text
faceplate.yaml  hierarchy, direction, gap, padding, alignment, and sizing
theme.css       colors, type, borders, textures, shadows, lamps, and needles
Coldth          state, behavior, accessibility, and interaction
```

Coldth should be able to generate a documented starter CSS file from a valid
faceplate. That stylesheet exposes stable semantic selectors for the root
faceplate, named frames, surfaces, and supported component parts. Editing the
generated CSS changes visual styling without requiring edits to the faceplate
layout.

Raw CSS remains an advanced escape hatch and cannot technically be prevented
from using browser layout properties. The supported contract reserves layout
ownership for the faceplate model. A future editor should guide ordinary users
through visual tokens and documented appearance properties while preserving
direct CSS access for theme designers.

Design this format for three equivalent authoring paths:

- hand-written theme packages;
- a future visual faceplate editor that reads and writes the normalized model;
- AI-generated themes produced from a concise authoring guide and a
  machine-readable schema.

Ship the contract with a versioned schema, a minimal valid theme, and explicit
instructions that generated themes may use only registered frames, surfaces,
presentations, and documented CSS parts. Theme packages still may not include
arbitrary HTML or executable JavaScript.

Completion means:

- a theme can declare its responsive frame tree in YAML;
- each document identifies `coldth.faceplate` and an explicit schema version;
- schema versions are negotiated independently of Coldth and package versions;
- invalid frame trees fail with useful path-specific errors;
- Coldth returns one normalized layout representation to clients;
- a starter stylesheet can be generated from the semantic frame tree;
- the generated CSS contains documented hooks without owning layout;
- bundled themes exercise hand-authored YAML and generated CSS; and
- the same model can be round-tripped by a future editor without losing
  meaningful author intent.

### 4. Standalone ten-band spectrum panel

Add a built-in spectrum presentation that renders the existing honest
ten-band analyzer data as a discrete 1980s-style panel. It must not depend on
EQ slider DOM or require the composite `tone-bank` component.

Black 1987 will use:

```text
standalone spectrum panel
plain ten-band faders
```

The existing integrated fader-ladder presentation remains available to themes
that want per-fader illumination.

Implemented: `coldth.presentation/ten-band-panel@1` now renders a skinnable
segmented post-EQ spectrum with an explicit dBFS scale. Black 1987 is its first
client and temporarily retains the integrated ladders while the faceplate
evolves.

### 5. LED marquee track display

Add a built-in `track-info` presentation for Black 1987 that:

- displays title, artist, and album in a receiver-style LED window;
- scrolls only when text exceeds the available width;
- pauses at readable boundaries;
- respects reduced-motion preferences; and
- exposes the complete text to assistive technology.

Theme CSS owns the font, LED color, glass, mask, and surrounding faceplate.
Coldth owns animation and accessibility behavior.

Implemented: Black 1987 selects
`coldth.presentation/matrix-marquee@1`. The trusted presentation scrolls only
when its complete title/artist/album line exceeds the viewport, pauses at both
ends, exposes the full line to assistive technology, and disables motion when
the browser requests reduced motion. The faceplate bundles Bitcount Grid
Single under the SIL Open Font License and owns its green matrix styling.

### 6. Preset button presentation and management

Add a second presentation for the existing presets component. It renders one
immediate-load button per preset, a visible active state, and a Save button.
The current dropdown presentation remains available for compact layouts.

Move preset administration to Settings:

- list presets;
- delete;
- import;
- export; and
- save or replace deliberately.

Reordering, renaming, and hiding presets are deferred until the button
presentation demonstrates a real need for them.

### 7. Theme chrome and packaged backgrounds

Exercise capabilities that should already belong to theme CSS:

- packaged background images and textures;
- per-surface padding;
- borders and border radius;
- panel shadows;
- inner control padding; and
- fully transparent or chrome-free surfaces.

Document the stable selectors needed to remove the default card treatment.
Add manifest or layout options only when CSS cannot express a requirement
safely.

### 8. Rotary controls and analog meters

Add Coldth-owned built-in presentations for:

- a preamp rotary knob (implemented and used by both bundled faceplates);
- a ten-band rotary EQ knob bank;
- rotary balance; and
- stereo analog VU meters.

Coldth owns pointer, touch, keyboard, focus, accessibility, value mapping, and
meter ballistics. Themes own bounded geometry and visual assets such as knob
faces, indicators, scales, needles, and panel materials.

### 9. Build the 1969 receiver faceplate

Use the new rotary and analog presentations to create the third bundled
faceplate. It should be structurally different from both existing themes, not
merely a wood-textured recolor.

This faceplate is the acceptance test for:

- presentation reuse;
- large visual assets;
- theme-controlled chrome;
- rotary interaction on desktop and touch screens;
- analog measurement motion; and
- layout fallback across orientations.

### 10. Component-face composition experiment

After all three complete faceplates exist, extract their proven component
treatments into reusable component faces. Do not invent the distributable
format before the bundled designs reveal the real styling boundaries.

The experiment should allow a local receiver recipe such as:

```text
EQ             Black 1987
Album artwork  Original Yellow
Stereo meters  1969
```

A complete receiver faceplate remains the simple default. Per-component
selection is an advanced override that creates a local custom recipe.

Completion means:

- component-face CSS is scoped to its mounted region and cannot leak into
  another component or the receiver shell;
- face assets resolve from the package that owns the face;
- a recipe may reference faces from multiple installed theme packages;
- Coldth records those direct references and prevents removing a package still
  used by a recipe;
- a missing or incompatible face falls back to the built-in presentation and
  face safely;
- selecting a complete receiver faceplate can reset component overrides to its
  coordinated defaults; and
- functionality, accessibility, and input behavior remain owned by Coldth,
  regardless of the selected face.

The exact manifest syntax and distribution contract remain deliberately
unsettled until this experiment is complete. This is a small direct-reference
graph, not a general-purpose dependency solver.

### 11. Contract review

After all three bundled faceplates and the component-face experiment work:

- remove abstractions that did not prove useful;
- decide whether component faces have earned a public package contract;
- promote stable component, part, and theme selectors into documentation;
- add representative third-party-style fixture themes to contract tests;
- review event and measurement shapes; and
- decide what must be frozen before API v1 can become stable.

## Intentionally deferred

### Third-party presentation plugins

Presentations are trusted executable code. Do not support third-party
installation until the built-in contracts have survived all three faceplates.

### Visualizer plugins

The standalone ten-band panel is a built-in presentation over existing
measurements, not a plugin system. Sandboxed, demoscene-style visualizers
remain a future platform described in
[visualizer plugins](visualizer-plugins.md).

### Additional era faceplates

1990s, 2000s, and 2010s designs are fertile future territory, including the
deliberately excessive, highly skinnable software-player aesthetic associated
with the Winamp era. They should wait until 1969, Black 1987, and Original
Yellow have established the core component and component-face boundaries.

### General dependency resolution

Coldth does not need npm-style package solving. During development, bundled
themes move with the unstable API. Theme package versions identify releases;
the eventual stable Coldth API version will define the compatibility boundary.
