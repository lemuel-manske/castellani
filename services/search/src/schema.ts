import Ajv from "ajv/dist/ajv.js";
import type { JSONSchemaType, ValidateFunction } from "ajv";

export interface SchemaValidator<T> {
  validate(value: unknown): value is T;
}

export function createSchemaValidator<T>(
  schema: JSONSchemaType<T>,
): SchemaValidator<T> {
  const ajv = new Ajv();
  const validate: ValidateFunction<T> = ajv.compile(schema);

  return {
    validate(value: unknown): value is T {
      return validate(value);
    },
  };
}
