# Coldth theme pain diary

This diary records friction discovered while designing the bundled faceplates.
It is evidence for later refactoring, not a queue of bugs that must all be
fixed immediately.

For each entry, record:

- what the design wanted;
- what the current architecture made awkward;
- any harmless temporary workaround;
- the suspected boundary; and
- which independent faceplates encounter the same problem.

A workaround appearing once may be a design choice. The same friction
appearing across multiple faceplates is architectural evidence.

## 2026-07-27 — Spectrum surface contains only status text

**Wanted**

Make spectrum an independently placeable measurement surface.

**Observed friction**

The existing `ten-band-overlay` presentation still reaches into the EQ
presentation and writes levels to its private `.band-level` elements. After
the shell gave spectrum its own surface, that surface displayed only
“10-band analyzer live.” The measurement is working, but its actual visual
output remains inside the faders.

**Temporary state**

Original Yellow retains fader-background illumination. Black 1987 suppresses
the empty spectrum surface while its composite fader-ladder presentation
consumes the same measurements.

**Suspected boundary**

Spectrum needs a self-contained presentation whose visual output lives
entirely inside the spectrum surface. An optional composite presentation may
still pair spectrum with EQ deliberately.

**Seen in**

- Original Yellow
- Black 1987

## 2026-07-27 — Independent surfaces still need shared chassis

**Wanted**

- Keep stereo meters and balance visually paired in some faceplates.
- Keep album artwork and AirPlay track information visually paired in some
  faceplates.
- Allow the same pairs to flow horizontally in one layout and vertically in
  another.
- Allow other faceplates to place each component independently.

**Observed friction**

Granular surfaces correctly separate state and placement, but every surface
currently receives its own card. CSS grid can place sibling cards beside one
another, but cannot give them one semantic panel, shared padding, shared
background, and shared border without brittle selector tricks.

**Temporary state**

Original Yellow displays meters and balance as adjacent independent cards.
Track information and artwork become separate cards when available.

**Suspected boundary**

This appears to be layout composition, not component nesting. Components
should remain independent siblings. A theme layout may need named, flat
surface groups that create a shared chassis and arrange member surfaces as a
row or column. Nested groups should not be assumed until a real design
requires them.

**Seen in**

- Original Yellow
- anticipated Black 1987 track display
- anticipated 1969 meter/control panel

**Resolution**

Implemented flat declarative surface groups. Original Yellow and Black 1987
now group meters with balance and artwork with track information. Landscape
uses row groups; portrait uses column groups. The component ownership model
did not need to change.

## 2026-07-27 — Flat groups are already becoming frames

**Wanted**

Compose substantially different faceplates without adding a new container
type for every arrangement.

**Observed friction**

A flat group can share one chassis, but it cannot describe a composed
faceplate. Themes will need nested groups, spacing, alignment, wrapping, and
content/container sizing.

**Suspected boundary**

Generalize the faceplate and its groups into a bounded, declarative auto-layout
frame tree. Use trusted surfaces as leaves. Do not add arbitrary HTML or
executable layout code.

**Seen in**

- Original Yellow
- Black 1987
- anticipated 1969 faceplate

## 2026-07-27 — Metadata availability is transitional

**Wanted**

Keep the now-playing chassis stable while an AirPlay session starts or changes
tracks.

**Observed friction**

AirPlay may report active playback before the next title, artist, or album
record arrives. Treating absent text as an unavailable component caused the
entire now-playing group to disappear during that transition.

**Resolution**

Keep track information visible while transport is playing and show an honest
waiting state. Artwork remains independently optional.
