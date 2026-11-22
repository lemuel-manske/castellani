import { describe, expect, it } from "vitest";
import {
  emptyPublicationFacts,
  isPublicationAuthorized,
  recordCompensation,
  recordPublicationDecision,
  recordReplayPublished,
  type PublicationIdentity,
} from "../../src/domain/publication.js";

const identity: PublicationIdentity = {
  archiveId: "archive-1",
  decisionVersion: 3,
  packageDigest: "sha256:package",
};

describe("publication facts", () => {
  it("does not authorize visibility until both independent facts match", () => {
    const decisionOnly = recordPublicationDecision(emptyPublicationFacts(), identity);
    expect(isPublicationAuthorized(decisionOnly)).toBe(false);

    const both = recordReplayPublished(decisionOnly, identity);
    expect(isPublicationAuthorized(both)).toBe(true);
  });

  it("accepts replay acknowledgement before the decision", () => {
    const replayOnly = recordReplayPublished(emptyPublicationFacts(), identity);
    expect(isPublicationAuthorized(replayOnly)).toBe(false);

    const both = recordPublicationDecision(replayOnly, identity);
    expect(isPublicationAuthorized(both)).toBe(true);
  });

  it("treats duplicate deliveries as idempotent", () => {
    const first = recordPublicationDecision(emptyPublicationFacts(), identity);
    const second = recordPublicationDecision(first, identity);
    expect(second).toBe(first);
  });

  it("rejects conflicting decision identities", () => {
    const facts = recordPublicationDecision(emptyPublicationFacts(), identity);
    expect(() =>
      recordPublicationDecision(facts, { ...identity, packageDigest: "sha256:other" }),
    ).toThrow("conflicting publication decision");
  });

  it("rejects replay acknowledgement for a different package", () => {
    const facts = recordPublicationDecision(emptyPublicationFacts(), identity);
    expect(() =>
      recordReplayPublished(facts, { ...identity, decisionVersion: 4 }),
    ).not.toThrow();
    const mismatched = recordReplayPublished(facts, { ...identity, decisionVersion: 4 });
    expect(isPublicationAuthorized(mismatched)).toBe(false);
  });

  it("keeps compensated archives permanently ineligible", () => {
    const facts = recordCompensation(
      recordReplayPublished(
        recordPublicationDecision(emptyPublicationFacts(), identity),
        identity,
      ),
    );
    expect(isPublicationAuthorized(facts)).toBe(false);
    expect(() => recordPublicationDecision(facts, identity)).toThrow(
      "a compensated archive cannot be published",
    );
  });
});
