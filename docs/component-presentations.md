# Component and presentation registry

The surrounding structural vocabulary and the input-to-effect behavior loop
are defined in the [receiver model](receiver-model.md).

## Status

The bundled receiver now renders every interactive or live-data surface
through the dependency-free browser registry. The application shell owns API
and event-stream coordination; presentations own their DOM and interaction
behavior.

## Runtime contract

A component describes semantic receiver state and its value shape:

```js
{
  id: "balance",
  valueType: "continuous-bipolar",
  capability: "balance"
}
```

A presentation is trusted browser code with a stable versioned identifier,
compatible value types, a bounded option schema, and a mount function:

```js
{
  id: "coldth.presentation/horizontal-slider@1",
  valueTypes: ["continuous-bipolar"],
  components: ["balance"],
  optionsSchema: { properties: {} },
  mount
}
```

Mounting returns the minimal control lifecycle:

```ts
interface MountedControl<T> {
  setValue(value: T): void;
  dispose(): void;
}
```

The host supplies state, limits, labels, and an intent callback through the
mount context. Presentations do not fetch the Coldth API themselves.

## Validation

The registry rejects malformed or duplicate identifiers, unknown components
or presentations, incompatible value shapes, invalid options, and mounted
presentations that do not return the control lifecycle.

This is runtime validation for bundled trusted code. Theme package validation
will use the same presentation descriptors before a declarative layout is
activated.

## Implemented built-ins

```text
eq       → coldth.presentation/vertical-fader@1
balance  → coldth.presentation/horizontal-slider@1
preamp   → coldth.presentation/preamp-slider@1
preamp   → coldth.presentation/rotary-knob@1
stereo-meters → coldth.presentation/led-bar@1
spectrum → coldth.presentation/ten-band-overlay@1
tone-bank → coldth.presentation/fader-ladder@1
track-info → coldth.presentation/now-playing-text@1
album-art → coldth.presentation/album-artwork@1
presets  → coldth.presentation/preset-selector@1
```

`tone-bank` is the first composite semantic component. It combines writable
ten-band EQ state with read-only ten-band spectrum measurements. Its
`fader-ladder@1` presentation renders one accessible fader and one discrete
level ladder per frequency. The options schema permits `8..40` segments and a
validated orientation; themes cannot replace its input or measurement code.

Presentations expose stable semantic `data-part` attributes for supported
visual styling. Classes remain implementation conveniences; faceplate CSS
should prefer the documented parts:

```text
meters      channel, channel-label, track, fill, peak, value
balance     left-label, right-label, legend, control, value
preamp      legend, control, value, knob, face
spectrum    status
track-info  state, title, byline
album-art   image
tone        band, value, track, level, control-group, control,
            ladder, segment, label
presets     heading, save, controls, list, load, export, delete,
            import, save-dialog
```

Parts are scoped through their surface:

```css
[data-surface="meters"] [data-part="peak"] {
  /* Visual treatment only. */
}
```

Presentation code owns DOM structure, accessibility labels, behavior, and
motion. A theme must not rely on the relative nesting or element type of a
part.

Presentations mount inside application-owned receiver surfaces. Track
information and album artwork are separate components observing the same
canonical metadata state, so either can be placed or omitted independently.

The Coldth Faceplate Language controls the physical frame tree containing
`meters`, `balance`, `preamp`, `spectrum`, `track-info`, `album-art`, `tone`,
and `presets`. It does not move presentation-generated DOM across component
boundaries or take ownership of the header and service status. Frames expose
stable `data-frame` hooks and collapse when every optional descendant is
unavailable.

## Testing

Pure registry behavior uses Node's built-in test runner and has no package
dependencies:

```sh
npm run test:js
```

Node is a development tool only. The Raspberry Pi serves native browser
modules and does not run Node in production.
