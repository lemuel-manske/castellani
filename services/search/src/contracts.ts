import { globSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";

import { isRecord, readJSON } from "./utils.js";

const require = createRequire(import.meta.url);
const Ajv2020 = require("ajv/dist/2020.js") as unknown as AjvConstructor;
const addFormats = require("ajv-formats") as unknown as AddFormats;

const CONTRACT_DIR_ENV = "SEARCH_CONTRACTS_DIR";

const MESSAGES_DIR = "messages";

const SCHEMA_GLOB = "*.v1.schema.json";

interface ValidateFunction {
  (value: unknown): boolean;
}

interface AjvInstance {
  addSchema(schema: object, key?: string): void;
  getSchema(key: string): ValidateFunction | undefined;
}

interface AjvConstructor {
  new (): AjvInstance;
}

type AddFormats = (ajv: AjvInstance) => void;

interface ValidatedMessage {
  type: string;
  version: 1;
  messageId: string;
  correlationId: string;
  occurredAt: string;
  payload: Record<string, unknown>;
}

let messageValidators: Map<string, ValidateFunction> | undefined;

function validateMessage(
  body: Uint8Array,
  expectedType?: string,
): ValidatedMessage | null {
  const validators = messageValidators ?? loadValidators();

  messageValidators = validators;

  const value = readJSON(body);

  if (!isRecord(value) || typeof value["type"] !== "string") {
    return null;
  }

  const messageType = expectedType ?? value["type"];
  const validator = validators.get(messageType);

  if (validator === undefined || !validator(value)) {
    return null;
  }

  return value as unknown as ValidatedMessage;
}

function loadValidators(): Map<string, ValidateFunction> {
  const directory = process.env[CONTRACT_DIR_ENV];

  if (directory === undefined || directory.trim() === "") {
    throw new Error(`${CONTRACT_DIR_ENV} must not be empty`);
  }

  const ajv = new Ajv2020();

  addFormats(ajv);

  const schemas = contractPaths(directory).map(readSchema);
  const validators = new Map<string, ValidateFunction>();

  for (const schema of schemas) {
    const schemaId = schema["$id"];

    if (typeof schemaId !== "string") {
      continue;
    }

    ajv.addSchema(schema, schemaId);
    ajv.addSchema(schema, `../${schemaId}`);
  }

  for (const schema of schemas) {
    const schemaId = schema["$id"];
    const messageType = schemaMessageType(schema);

    if (typeof schemaId !== "string" || messageType === undefined) {
      continue;
    }

    const validator = ajv.getSchema(schemaId);

    if (validator === undefined) {
      throw new Error(`missing validator for ${schemaId}`);
    }

    validators.set(messageType, validator);
  }

  return validators;
}

function contractPaths(directory: string): string[] {
  const shared = globSync(join(directory, SCHEMA_GLOB)).sort();
  const messages = globSync(join(directory, MESSAGES_DIR, SCHEMA_GLOB)).sort();

  return [...shared, ...messages];
}

function readSchema(path: string): Record<string, unknown> {
  const schema: unknown = JSON.parse(readFileSync(path, "utf8"));

  if (!isRecord(schema)) {
    throw new Error(`invalid contract ${path}`);
  }

  return schema;
}

function schemaMessageType(
  schema: Record<string, unknown>,
): string | undefined {
  const properties = schema["properties"];

  if (!isRecord(properties)) {
    return undefined;
  }

  const type = properties["type"];

  if (!isRecord(type) || typeof type["const"] !== "string") {
    return undefined;
  }

  return type["const"];
}

export { validateMessage };
