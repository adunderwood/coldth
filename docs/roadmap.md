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
3 removes that remaining coupling.

### 2. Split track information and album artwork — implemented

Replace the combined metadata presentation with two semantic components that
observe the same canonical metadata state:

- `track-info` — title, artist, album, and transport state;
- `album-art` — artwork availability and same-origin artwork URL.

Provide conventional built-in presentations for both. Absence of metadata or
artwork must collapse cleanly without leaving an empty decorative panel.

Both components now mount and advertise availability independently while
observing the same canonical metadata and transport state.

### 3. Standalone ten-band spectrum panel

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

### 4. LED marquee track display

Add a built-in `track-info` presentation for Black 1987 that:

- displays title, artist, and album in a receiver-style LED window;
- scrolls only when text exceeds the available width;
- pauses at readable boundaries;
- respects reduced-motion preferences; and
- exposes the complete text to assistive technology.

Theme CSS owns the font, LED color, glass, mask, and surrounding faceplate.
Coldth owns animation and accessibility behavior.

### 5. Preset button presentation and management

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

### 6. Theme chrome and packaged backgrounds

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

### 7. Rotary controls and analog meters

Add Coldth-owned built-in presentations for:

- a ten-band rotary EQ knob bank;
- rotary balance; and
- stereo analog VU meters.

Coldth owns pointer, touch, keyboard, focus, accessibility, value mapping, and
meter ballistics. Themes own bounded geometry and visual assets such as knob
faces, indicators, scales, needles, and panel materials.

### 8. Build the 1969 receiver faceplate

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

### 9. Component-face composition experiment

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

### 10. Contract review

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
