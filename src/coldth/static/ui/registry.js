export class RegistryError extends Error {}

function assertIdentifier(value, label) {
  if (typeof value !== "string" || !/^[a-z0-9.-]+(?:\/[a-z0-9-]+)?(?:@\d+)?$/.test(value)) {
    throw new RegistryError(`${label} must be a stable lowercase identifier`);
  }
}

function validateOption(name, value, rule) {
  if (rule.type === "number") {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new RegistryError(`Option "${name}" must be a number`);
    }
    if (rule.minimum !== undefined && value < rule.minimum) {
      throw new RegistryError(`Option "${name}" must be at least ${rule.minimum}`);
    }
    if (rule.maximum !== undefined && value > rule.maximum) {
      throw new RegistryError(`Option "${name}" must be at most ${rule.maximum}`);
    }
  } else if (rule.type === "string") {
    if (typeof value !== "string") {
      throw new RegistryError(`Option "${name}" must be text`);
    }
  } else if (rule.type === "boolean") {
    if (typeof value !== "boolean") {
      throw new RegistryError(`Option "${name}" must be true or false`);
    }
  } else {
    throw new RegistryError(`Option schema for "${name}" has an unsupported type`);
  }
  if (rule.enum && !rule.enum.includes(value)) {
    throw new RegistryError(
      `Option "${name}" must be one of: ${rule.enum.join(", ")}`,
    );
  }
}

function validateOptions(schema = {}, supplied = {}) {
  if (!supplied || typeof supplied !== "object" || Array.isArray(supplied)) {
    throw new RegistryError("Presentation options must be an object");
  }
  const properties = schema.properties || {};
  const unknown = Object.keys(supplied).filter((name) => !(name in properties));
  if (unknown.length) {
    throw new RegistryError(`Unknown presentation option: ${unknown.join(", ")}`);
  }
  const options = {};
  for (const [name, rule] of Object.entries(properties)) {
    if (name in supplied) {
      validateOption(name, supplied[name], rule);
      options[name] = supplied[name];
    } else if ("default" in rule) {
      options[name] = rule.default;
    } else if ((schema.required || []).includes(name)) {
      throw new RegistryError(`Missing presentation option: ${name}`);
    }
  }
  return Object.freeze(options);
}

export class ControlRegistry {
  constructor() {
    this.components = new Map();
    this.presentations = new Map();
  }

  registerComponent(component) {
    assertIdentifier(component?.id, "Component id");
    if (typeof component.valueType !== "string" || !component.valueType) {
      throw new RegistryError("Component valueType is required");
    }
    if (this.components.has(component.id)) {
      throw new RegistryError(`Component already registered: ${component.id}`);
    }
    this.components.set(component.id, Object.freeze({ ...component }));
  }

  registerPresentation(presentation) {
    assertIdentifier(presentation?.id, "Presentation id");
    if (!Array.isArray(presentation.valueTypes) || !presentation.valueTypes.length) {
      throw new RegistryError("Presentation valueTypes are required");
    }
    if (typeof presentation.mount !== "function") {
      throw new RegistryError("Presentation mount function is required");
    }
    if (this.presentations.has(presentation.id)) {
      throw new RegistryError(`Presentation already registered: ${presentation.id}`);
    }
    this.presentations.set(presentation.id, Object.freeze({ ...presentation }));
  }

  resolve(componentId, presentationId, suppliedOptions = {}) {
    const component = this.components.get(componentId);
    if (!component) throw new RegistryError(`Unknown component: ${componentId}`);
    const presentation = this.presentations.get(presentationId);
    if (!presentation) {
      throw new RegistryError(`Unknown presentation: ${presentationId}`);
    }
    if (!presentation.valueTypes.includes(component.valueType)) {
      throw new RegistryError(
        `${presentationId} does not support ${component.valueType} components`,
      );
    }
    if (
      presentation.components &&
      !presentation.components.includes(component.id)
    ) {
      throw new RegistryError(
        `${presentationId} does not support component ${component.id}`,
      );
    }
    return {
      component,
      presentation,
      options: validateOptions(presentation.optionsSchema, suppliedOptions),
    };
  }

  mount({ component, presentation, root, options = {}, context = {} }) {
    if (!root) throw new RegistryError("A presentation root element is required");
    const resolved = this.resolve(component, presentation, options);
    const control = resolved.presentation.mount({
      root,
      component: resolved.component,
      options: resolved.options,
      context,
    });
    if (!control || typeof control.setValue !== "function") {
      throw new RegistryError(`${presentation} returned an invalid control`);
    }
    return control;
  }
}
