export interface PublicationIdentity {
  archiveId: string;
  decisionVersion: number;
  packageDigest: string;
}

export interface PublicationFacts {
  decision: PublicationIdentity | null;
  replay: PublicationIdentity | null;
  compensated: boolean;
}

export const emptyPublicationFacts = (): PublicationFacts => ({
  decision: null,
  replay: null,
  compensated: false,
});

export class PublicationConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PublicationConflictError";
  }
}

function sameIdentity(left: PublicationIdentity, right: PublicationIdentity): boolean {
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

/**
 * Records the Coordinator's irreversible publication decision.
 * Re-delivery of the same decision is idempotent; a conflicting fact is rejected.
 */
export function recordPublicationDecision(
  facts: PublicationFacts,
  identity: PublicationIdentity,
): PublicationFacts {
  validateIdentity(identity);

  if (facts.compensated) {
    throw new PublicationConflictError("a compensated archive cannot be published");
  }

  if (facts.replay && !sameIdentity(facts.replay, identity)) {
    throw new PublicationConflictError("publication decision conflicts with replay acknowledgement");
  }

  if (facts.decision) {
    if (!sameIdentity(facts.decision, identity)) {
      throw new PublicationConflictError("conflicting publication decision");
    }
    return facts;
  }

  return { ...facts, decision: { ...identity } };
}

/**
 * Records Capture's durable replay-publication acknowledgement.
 * This fact may arrive before the Coordinator's decision event.
 */
export function recordReplayPublished(
  facts: PublicationFacts,
  identity: PublicationIdentity,
): PublicationFacts {
  validateIdentity(identity);

  if (facts.compensated) {
    throw new PublicationConflictError("a compensated archive cannot be replay-published");
  }

  if (facts.decision && !sameIdentity(facts.decision, identity)) {
    throw new PublicationConflictError("replay acknowledgement conflicts with publication decision");
  }

  if (facts.replay) {
    if (!sameIdentity(facts.replay, identity)) {
      throw new PublicationConflictError("conflicting replay publication");
    }
    return facts;
  }

  return { ...facts, replay: { ...identity } };
}

/** Compensation and publication are mutually exclusive terminal decisions. */
export function recordCompensation(facts: PublicationFacts): PublicationFacts {
  if (facts.decision || facts.replay) {
    throw new PublicationConflictError("a publication fact prevents compensation");
  }
  return facts.compensated ? facts : { ...facts, compensated: true };
}

export function isPublicationAuthorized(facts: PublicationFacts): boolean {
  return (
    !facts.compensated &&
    facts.decision !== null &&
    facts.replay !== null &&
    sameIdentity(facts.decision, facts.replay)
  );
}
