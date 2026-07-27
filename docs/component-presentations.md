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

The stable styling surface includes `.tone-strip`, `.tone-strip-control`,
`.tone-fader`, `.level-ladder`, `.level-ladder i`, `.active`, and the
`data-zone` values `normal`, `warm`, and `hot`.

The presentations generate the same stable classes and accessibility labels
used by the original receiver. Existing CSS themes and responsive layouts
therefore continue to work without knowing about registry internals.

Presentations mount inside application-owned receiver surfaces. Track
information and album artwork are separate components observing the same
canonical metadata state, so either can be placed or omitted independently.

Declarative theme layout controls the physical flow of `meters`, `balance`,
`spectrum`, `track-info`, `album-art`, `tone`, and `presets`. It does not move
presentation-generated DOM across component boundaries or take ownership of
the header and service status. Layouts may explicitly hide optional
observational surfaces; omitting a surface from `flow` uses its safe fallback
position instead.

Flat surface groups let independent sibling surfaces share one chassis.
Groups own layout direction and provide a stable `data-layout-group` styling
target; member surfaces retain their original components, presentations, and
state ownership. A surface belongs to at most one group per layout. Empty
groups collapse when every optional member is unavailable.

## Testing

Pure registry behavior uses Node's built-in test runner and has no package
dependencies:

```sh
npm run test:js
```

Node is a development tool only. The Raspberry Pi serves native browser
modules and does not run Node in production.
