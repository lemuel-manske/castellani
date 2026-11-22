import { expect, it } from "vitest";
import {
  emptyPublicationFacts,
  isPublicationAuthorized,
  recordCompensation,
  recordPublicationDecision,
  recordReplayPublished,
} from "../../src/domain/publication.js";
import type { PublicationIdentity } from "../../src/domain.js";

const identity: PublicationIdentity = {
  archiveId: "archive-1",
  decisionVersion: 3,
  packageDigest: "sha256:package",
};

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
  expect(recordPublicationDecision(first, identity)).toBe(first);
});

it("rejects conflicting decision identities", () => {
  const facts = recordPublicationDecision(emptyPublicationFacts(), identity);
  expect(() =>
    recordPublicationDecision(facts, { ...identity, packageDigest: "sha256:other" }),
  ).toThrow("conflicting publication decision");
});

it("rejects a replay acknowledgement that conflicts with an earlier decision", () => {
  const facts = recordPublicationDecision(emptyPublicationFacts(), identity);
  expect(() =>
    recordReplayPublished(facts, { ...identity, decisionVersion: 4 }),
  ).toThrow("replay acknowledgement conflicts");
});

it("rejects a decision that conflicts with an earlier replay acknowledgement", () => {
  const facts = recordReplayPublished(emptyPublicationFacts(), identity);
  expect(() =>
    recordPublicationDecision(facts, { ...identity, packageDigest: "sha256:other" }),
  ).toThrow("publication decision conflicts");
});

it("keeps compensated archives permanently ineligible", () => {
  const facts = recordCompensation(emptyPublicationFacts());
  expect(isPublicationAuthorized(facts)).toBe(false);
  expect(() => recordPublicationDecision(facts, identity)).toThrow(
    "a compensated archive cannot be published",
  );
});

it("rejects compensation after a publication fact has been recorded", () => {
  const facts = recordPublicationDecision(emptyPublicationFacts(), identity);
  expect(() => recordCompensation(facts)).toThrow("a publication fact prevents compensation");
});
