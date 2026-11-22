import type {
  CompensationDecision,
  PublicationFacts,
  PublicationIdentity,
} from "../domain.js";

const emptyPublicationFacts = (): PublicationFacts => ({
  publicationDecision: null,
  replayPublication: null,
  compensationDecision: null,
});

class PublicationConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PublicationConflictError";
  }
}

function sameIdentity(
  left: PublicationIdentity,
  right: PublicationIdentity,
): boolean {
  return (
    left.archiveId === right.archiveId &&
    left.decisionVersion === right.decisionVersion &&
    left.packageDigest === right.packageDigest
  );
}

function validateIdentity(identity: PublicationIdentity): void {
  if (
    !identity.archiveId ||
    !identity.packageDigest ||
    !Number.isSafeInteger(identity.decisionVersion) ||
    identity.decisionVersion < 1
  ) {
    throw new PublicationConflictError("invalid publication identity");
  }
}

/** Records the Coordinator's irreversible publication decision. */
function recordPublicationDecision(
  facts: PublicationFacts,
  identity: PublicationIdentity,
): PublicationFacts {
  validateIdentity(identity);

  if (facts.compensationDecision !== null) {
    throw new PublicationConflictError(
      "a compensated archive cannot be published",
    );
  }

  if (
    facts.replayPublication &&
    !sameIdentity(facts.replayPublication, identity)
  ) {
    throw new PublicationConflictError(
      "publication decision conflicts with replay acknowledgement",
    );
  }

  if (facts.publicationDecision) {
    if (!sameIdentity(facts.publicationDecision, identity)) {
      throw new PublicationConflictError("conflicting publication decision");
    }

    return facts;
  }

  return { ...facts, publicationDecision: { ...identity } };
}

/** Records Capture's durable replay-publication acknowledgement. */
function recordReplayPublished(
  facts: PublicationFacts,
  identity: PublicationIdentity,
): PublicationFacts {
  validateIdentity(identity);

  if (facts.compensationDecision !== null) {
    throw new PublicationConflictError(
      "a compensated archive cannot be replay-published",
    );
  }

  if (
    facts.publicationDecision &&
    !sameIdentity(facts.publicationDecision, identity)
  ) {
    throw new PublicationConflictError(
      "replay acknowledgement conflicts with publication decision",
    );
  }

  if (facts.replayPublication) {
    if (!sameIdentity(facts.replayPublication, identity)) {
      throw new PublicationConflictError("conflicting replay publication");
    }

    return facts;
  }

  return { ...facts, replayPublication: { ...identity } };
}

/** Compensation and publication are mutually exclusive terminal decisions. */
function recordCompensationDecision(
  facts: PublicationFacts,
  decision: CompensationDecision,
): PublicationFacts {
  if (
    !decision.archiveId ||
    !decision.reasonCode ||
    !Number.isSafeInteger(decision.decisionVersion) ||
    decision.decisionVersion < 1
  ) {
    throw new PublicationConflictError("invalid compensation decision");
  }

  if (facts.publicationDecision || facts.replayPublication) {
    throw new PublicationConflictError(
      "a publication fact prevents compensation",
    );
  }

  if (facts.compensationDecision) {
    const previous = facts.compensationDecision;

    if (
      previous.archiveId !== decision.archiveId ||
      previous.decisionVersion !== decision.decisionVersion ||
      previous.reasonCode !== decision.reasonCode
    ) {
      throw new PublicationConflictError("conflicting compensation decision");
    }

    return facts;
  }

  return { ...facts, compensationDecision: { ...decision } };
}

function isPublicationAuthorized(facts: PublicationFacts): boolean {
  return (
    facts.compensationDecision === null &&
    facts.publicationDecision !== null &&
    facts.replayPublication !== null &&
    sameIdentity(facts.publicationDecision, facts.replayPublication)
  );
}

export {
  PublicationConflictError,
  emptyPublicationFacts,
  isPublicationAuthorized,
  recordCompensationDecision,
  recordPublicationDecision,
  recordReplayPublished,
};
