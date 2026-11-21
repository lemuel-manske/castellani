import { readFileSync } from "node:fs";

import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import { type ArtifactRef, type PageCaptured, type PublicationFact, DocumentError } from "../indexing/model.js";
import type { Manifest, ManifestParser } from "../reconciliation/reconciler.js";

/**
 * Repository `contracts/` directory. Images mirror the repository layout
 * (`/srv/contracts`, `/srv/services/search/dist`), so the same relative path
 * works for sources, build output, and containers.
 */
const CONTRACTS = new URL("../../../../contracts/", import.meta.url);

const SCHEMAS = {
  PageCaptured: "page-captured.v1.schema.json",
  ArchivePublicationDecided: "archive-publication-decided.v1.schema.json",
  ArchivePublished: "archive-published.v1.schema.json",
  ArchiveCompensationDecided: "archive-compensation-decided.v1.schema.json",
  CrawlCompleted: "crawl-completed.v1.schema.json",
  SearchCompensated: "search-compensated.v1.schema.json",
  SearchIndexingCompleted: "search-indexing-completed.v1.schema.json",
  SearchReady: "search-ready.v1.schema.json",
} as const;

export type MessageType = keyof typeof SCHEMAS;

export class InvalidMessageError extends Error {}

type Envelope = { messageId: string; correlationId: string; type: string; version: number; payload: object };

export type ArchiveFactEvent = PublicationFact & { messageId: string; archiveId: string };

export type CompensationEvent = { messageId: string; archiveId: string; decisionVersion: number; reasonCode: string };

export type CrawlCompletedEvent = {
  messageId: string;
  archiveId: string;
  manifest: ArtifactRef;
  manifestDigest: string;
};

export class Contracts implements ManifestParser {
  private readonly envelope: ValidateFunction;
  private readonly manifest: ValidateFunction;
  private readonly validators: Record<MessageType, ValidateFunction>;

  constructor(root: URL = CONTRACTS) {
    const ajv = new Ajv2020({ allErrors: false, strict: true });
    addFormats.default(ajv);

    // Relative `$id`s plus `../archive-manifest...` refs: register the
    // manifest under both spellings so references resolve either way.
    const manifest = load(root, "archive-manifest.v1.schema.json");
    ajv.addSchema(manifest, "archive-manifest.v1.schema.json");
    ajv.addSchema({ ...manifest, $id: "../archive-manifest.v1.schema.json" });

    const compiledManifest = ajv.getSchema("archive-manifest.v1.schema.json");

    if (compiledManifest === undefined) {
      throw new Error("archive manifest schema did not compile");
    }

    this.manifest = compiledManifest;
    this.envelope = ajv.compile(load(root, "messages/envelope.v1.schema.json"));
    this.validators = Object.fromEntries(
      Object.entries(SCHEMAS).map(([type, file]) => [type, ajv.compile(load(root, `messages/${file}`))]),
    ) as Record<MessageType, ValidateFunction>;
  }

  /** Validates the envelope and returns its routing identity. */
  envelopeOf(message: unknown): { messageId: string; type: string } {
    if (!this.envelope(message)) {
      throw new InvalidMessageError(`invalid envelope: ${errors(this.envelope)}`);
    }

    return message as Envelope;
  }

  parsePageCaptured(message: unknown): PageCaptured {
    const { messageId, payload } = this.validate("PageCaptured", message);

    return { messageId, ...(payload as Omit<PageCaptured, "messageId">) };
  }

  parseArchiveFact(type: "ArchivePublicationDecided" | "ArchivePublished", message: unknown): ArchiveFactEvent {
    const { messageId, payload } = this.validate(type, message);
    const { archiveId, decisionVersion, packageDigest } = payload as {
      archiveId: string;
      decisionVersion: number;
      packageDigest: string;
    };

    return { messageId, archiveId, decisionVersion, packageDigest };
  }

  parseCompensation(message: unknown): CompensationEvent {
    const { messageId, payload } = this.validate("ArchiveCompensationDecided", message);
    const { archiveId, decisionVersion, reasonCode } = payload as {
      archiveId: string;
      decisionVersion: number;
      reasonCode: string;
    };

    return { messageId, archiveId, decisionVersion, reasonCode };
  }

  parseCrawlCompleted(message: unknown): CrawlCompletedEvent {
    const { messageId, payload } = this.validate("CrawlCompleted", message);
    const { archiveId, manifest, manifestDigest } = payload as {
      archiveId: string;
      manifest: ArtifactRef;
      manifestDigest: string;
    };

    return { messageId, archiveId, manifest, manifestDigest };
  }

  /** Validates a final crawl manifest document against its published schema. */
  parseManifest(document: unknown): Manifest {
    if (!this.manifest(document)) {
      throw new DocumentError(`invalid manifest: ${errors(this.manifest)}`);
    }

    return document as Manifest;
  }

  /** Validates a message this service emits; a failure is a programming error. */
  assertOutgoing(type: MessageType, message: unknown): void {
    const validate = this.validators[type];

    if (!validate(message)) {
      throw new Error(`refusing to emit invalid ${type}: ${errors(validate)}`);
    }
  }

  private validate(type: MessageType, message: unknown): Envelope {
    const validate = this.validators[type];

    if (!validate(message)) {
      throw new InvalidMessageError(`invalid ${type}: ${errors(validate)}`);
    }

    const envelope = message as Envelope;
    const { archiveId } = envelope.payload as { archiveId: string };

    if (envelope.correlationId !== archiveId) {
      throw new InvalidMessageError(`${type} correlationId must equal payload.archiveId`);
    }

    return envelope;
  }
}

function errors(validate: ValidateFunction): string {
  return (validate.errors ?? []).map((error) => `${error.instancePath || "/"} ${error.message}`).join("; ");
}

function load(root: URL, path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(new URL(path, root), "utf8")) as Record<string, unknown>;
}
