import { readFileSync } from "node:fs";

import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import type { PageCaptured } from "../indexing/model.js";

/**
 * Repository `contracts/` directory. Images mirror the repository layout
 * (`/srv/contracts`, `/srv/services/search/dist`), so the same relative path
 * works for sources, build output, and containers.
 */
const CONTRACTS = new URL("../../../../contracts/", import.meta.url);

export class InvalidMessageError extends Error {}

type Envelope = { type: string; version: number };

export class Contracts {
  private readonly envelope: ValidateFunction;
  private readonly pageCaptured: ValidateFunction;

  constructor(root: URL = CONTRACTS) {
    const ajv = new Ajv2020({ allErrors: false, strict: true });
    addFormats.default(ajv);

    // Relative `$id`s plus `../archive-manifest...` refs: register the
    // manifest under both spellings so references resolve either way.
    const manifest = load(root, "archive-manifest.v1.schema.json");
    ajv.addSchema(manifest, "archive-manifest.v1.schema.json");
    ajv.addSchema({ ...manifest, $id: "../archive-manifest.v1.schema.json" });

    this.envelope = ajv.compile(load(root, "messages/envelope.v1.schema.json"));
    this.pageCaptured = ajv.compile(load(root, "messages/page-captured.v1.schema.json"));
  }

  /** Validates the envelope and returns its routing identity. */
  envelopeOf(message: unknown): Envelope {
    if (!this.envelope(message)) {
      throw new InvalidMessageError(`invalid envelope: ${this.errors(this.envelope)}`);
    }

    return message as Envelope;
  }

  parsePageCaptured(message: unknown): PageCaptured {
    if (!this.pageCaptured(message)) {
      throw new InvalidMessageError(`invalid PageCaptured: ${this.errors(this.pageCaptured)}`);
    }

    const { messageId, correlationId, payload } = message as {
      messageId: string;
      correlationId: string;
      payload: Omit<PageCaptured, "messageId">;
    };

    if (correlationId !== payload.archiveId) {
      throw new InvalidMessageError("PageCaptured correlationId must equal payload.archiveId");
    }

    return { messageId, ...payload };
  }

  private errors(validate: ValidateFunction): string {
    return (validate.errors ?? []).map((error) => `${error.instancePath || "/"} ${error.message}`).join("; ");
  }
}

function load(root: URL, path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(new URL(path, root), "utf8")) as Record<string, unknown>;
}
