# Component and presentation registry

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
metadata → coldth.presentation/now-playing-display@1
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

## Testing

Pure registry behavior uses Node's built-in test runner and has no package
dependencies:

```sh
npm run test:js
```

Node is a development tool only. The Raspberry Pi serves native browser
modules and does not run Node in production.
