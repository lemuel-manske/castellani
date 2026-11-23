import { createSchemaValidator } from "./schema.js";

/**
 * Search domain vocabulary.
 *
 * Keep domain concepts and contracts here.
 */

interface PublicationIdentity {
  archiveId: string;
  decisionVersion: number;
  packageDigest: string;
}

interface CompensationDecision {
  archiveId: string;
  decisionVersion: number;
  reasonCode: string;
}

interface PublicationFacts {
  publicationDecision: PublicationIdentity | null;
  replayPublication: PublicationIdentity | null;
  compensationDecision: CompensationDecision | null;
}

type IndexingOutcome =
  | "PENDING"
  | "PROCESSING"
  | "INDEXED"
  | "UNSUPPORTED"
  | "FAILED";

type NonTerminalIndexingOutcome = Extract<
  IndexingOutcome,
  "PENDING" | "PROCESSING"
>;

type TerminalIndexingOutcome = Extract<
  IndexingOutcome,
  "INDEXED" | "UNSUPPORTED" | "FAILED"
>;

interface ManifestSnapshot {
  snapshotId: string;
}

interface SnapshotLedgerEntry {
  snapshotId: string;
  outcome: IndexingOutcome;
}

interface ManifestReconciliation {
  expectedCount: number;
  terminalCount: number;
  missingSnapshotIds: string[];
  unexpectedSnapshotIds: string[];
  complete: boolean;
}

const PublicationIdentitySchema = {
  type: "object",
  properties: {
    archiveId: { type: "string", minLength: 1 },
    decisionVersion: { type: "integer", minimum: 1 },
    packageDigest: { type: "string", minLength: 1 },
  },
  required: ["archiveId", "decisionVersion", "packageDigest"],
  additionalProperties: false,
} as const;

const publicationIdentityValidator = createSchemaValidator<PublicationIdentity>(
  PublicationIdentitySchema,
);

function isPublicationIdentity(value: unknown): value is PublicationIdentity {
  return publicationIdentityValidator.validate(value);
}

const CompensationDecisionSchema = {
  type: "object",
  properties: {
    archiveId: { type: "string", minLength: 1 },
    decisionVersion: { type: "integer", minimum: 1 },
    reasonCode: { type: "string", minLength: 1 },
  },
  required: ["archiveId", "decisionVersion", "reasonCode"],
  additionalProperties: false,
} as const;

const compensationDecisionValidator =
  createSchemaValidator<CompensationDecision>(CompensationDecisionSchema);

function isCompensationDecision(value: unknown): value is CompensationDecision {
  return compensationDecisionValidator.validate(value);
}

export {
  CompensationDecisionSchema,
  isCompensationDecision,
  isPublicationIdentity,
  PublicationIdentitySchema,
};

export type {
  CompensationDecision,
  IndexingOutcome,
  ManifestReconciliation,
  ManifestSnapshot,
  NonTerminalIndexingOutcome,
  PublicationFacts,
  PublicationIdentity,
  SnapshotLedgerEntry,
  TerminalIndexingOutcome,
};
