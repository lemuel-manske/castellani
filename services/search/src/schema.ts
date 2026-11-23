import { createRequire } from "node:module";
import type { JSONSchemaType, ValidateFunction } from "ajv";

interface AjvInstance {
  compile<T>(schema: JSONSchemaType<T>): ValidateFunction<T>;
}

interface AjvConstructor {
  new (): AjvInstance;
}

const require = createRequire(import.meta.url);
const Ajv = require("ajv") as unknown as AjvConstructor;

export interface SchemaValidator<T> {
  validate(value: unknown): value is T;
}

export function createSchemaValidator<T>(
  schema: JSONSchemaType<T>,
): SchemaValidator<T> {
  const ajv = new Ajv();
  const validate = ajv.compile(schema);

  return {
    validate(value: unknown): value is T {
      return validate(value);
    },
  };
}
