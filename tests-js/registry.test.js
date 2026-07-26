import test from "node:test";
import assert from "node:assert/strict";

import { ControlRegistry, RegistryError } from "../src/coldth/static/ui/registry.js";
import {
  BALANCE_COMPONENT,
  BALANCE_SLIDER_PRESENTATION,
  EQ_COMPONENT,
  EQ_FADER_PRESENTATION,
  LED_METERS_PRESENTATION,
  METADATA_COMPONENT,
  METERS_COMPONENT,
  NOW_PLAYING_PRESENTATION,
  PRESETS_COMPONENT,
  PRESET_SELECTOR_PRESENTATION,
  SPECTRUM_COMPONENT,
  SPECTRUM_OVERLAY_PRESENTATION,
  registerBuiltins,
} from "../src/coldth/static/ui/builtins.js";

test("built-in presentations resolve against semantic components", () => {
  const registry = new ControlRegistry();
  registerBuiltins(registry);

  const eq = registry.resolve(EQ_COMPONENT, EQ_FADER_PRESENTATION);
  const balance = registry.resolve(
    BALANCE_COMPONENT,
    BALANCE_SLIDER_PRESENTATION,
  );
  const meters = registry.resolve(METERS_COMPONENT, LED_METERS_PRESENTATION);
  const spectrum = registry.resolve(
    SPECTRUM_COMPONENT,
    SPECTRUM_OVERLAY_PRESENTATION,
  );
  const metadata = registry.resolve(
    METADATA_COMPONENT,
    NOW_PLAYING_PRESENTATION,
  );
  const presets = registry.resolve(
    PRESETS_COMPONENT,
    PRESET_SELECTOR_PRESENTATION,
  );

  assert.equal(eq.component.valueType, "band-collection");
  assert.deepEqual(eq.options, { orientation: "responsive" });
  assert.equal(balance.component.valueType, "continuous-bipolar");
  assert.deepEqual(meters.options, { releasePerFrame: 0.7 });
  assert.equal(spectrum.component.valueType, "band-measurements");
  assert.equal(metadata.component.valueType, "metadata-state");
  assert.equal(presets.component.valueType, "preset-collection");
});

test("presentation options are schema validated", () => {
  const registry = new ControlRegistry();
  registerBuiltins(registry);

  assert.throws(
    () =>
      registry.resolve(EQ_COMPONENT, EQ_FADER_PRESENTATION, {
        orientation: "diagonal",
      }),
    /must be one of/,
  );
  assert.throws(
    () =>
      registry.resolve(EQ_COMPONENT, EQ_FADER_PRESENTATION, {
        rotationSpeed: 12,
      }),
    /Unknown presentation option/,
  );
  assert.throws(
    () =>
      registry.resolve(METERS_COMPONENT, LED_METERS_PRESENTATION, {
        releasePerFrame: 0,
      }),
    /at least/,
  );
});

test("incompatible component and presentation pairs are rejected", () => {
  const registry = new ControlRegistry();
  registerBuiltins(registry);

  assert.throws(
    () => registry.resolve(BALANCE_COMPONENT, EQ_FADER_PRESENTATION),
    /does not support continuous-bipolar/,
  );
});

test("duplicate and malformed registrations are rejected", () => {
  const registry = new ControlRegistry();
  registerBuiltins(registry);

  assert.throws(
    () =>
      registry.registerComponent({
        id: EQ_COMPONENT,
        valueType: "band-collection",
      }),
    RegistryError,
  );
  assert.throws(
    () =>
      registry.registerComponent({
        id: "Bad Component",
        valueType: "continuous",
      }),
    /stable lowercase identifier/,
  );
});

test("mounted presentations must return the control lifecycle", () => {
  const registry = new ControlRegistry();
  registry.registerComponent({ id: "test", valueType: "continuous" });
  registry.registerPresentation({
    id: "coldth.presentation/broken@1",
    valueTypes: ["continuous"],
    optionsSchema: { properties: {} },
    mount() {
      return {};
    },
  });

  assert.throws(
    () =>
      registry.mount({
        component: "test",
        presentation: "coldth.presentation/broken@1",
        root: {},
      }),
    /returned an invalid control/,
  );
});
