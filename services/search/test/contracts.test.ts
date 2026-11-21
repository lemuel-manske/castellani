import { describe, expect, test } from "vitest";

import { Contracts, InvalidMessageError } from "../src/messaging/contracts.js";
import { pageCapturedMessage } from "./support/events.js";

const ARTIFACT = {
  bucket: "castellani-archive-artifacts",
  key: "a.warc.gz",
  sha256: "a".repeat(64),
  sizeBytes: 10,
};

describe("PageCaptured contract", () => {
  test("a message matching the published schema is accepted", () => {
    const contracts = new Contracts();
    const message = pageCapturedMessage({ archiveId: "archive-1", snapshotId: "s-1", warcArtifacts: [ARTIFACT] });

    const event = contracts.parsePageCaptured(message);

    expect(event).toMatchObject({
      messageId: message.messageId,
      archiveId: "archive-1",
      snapshotId: "s-1",
      warcArtifacts: [ARTIFACT],
    });
  });

  test("a message without WARC artifacts is rejected", () => {
    const contracts = new Contracts();
    const message = pageCapturedMessage({ warcArtifacts: [] });

    expect(() => contracts.parsePageCaptured(message)).toThrow(InvalidMessageError);
  });

  test("an artifact reference with an invalid digest is rejected", () => {
    const contracts = new Contracts();
    const message = pageCapturedMessage({ warcArtifacts: [{ ...ARTIFACT, sha256: "not-a-digest" }] });

    expect(() => contracts.parsePageCaptured(message)).toThrow(InvalidMessageError);
  });

  test("a correlation ID different from the archive ID is rejected", () => {
    const contracts = new Contracts();
    const message = { ...pageCapturedMessage({ warcArtifacts: [ARTIFACT] }), correlationId: "unrelated" };

    expect(() => contracts.parsePageCaptured(message)).toThrow(InvalidMessageError);
  });

  test("an unsupported envelope version is rejected", () => {
    const contracts = new Contracts();
    const message = { ...pageCapturedMessage({ warcArtifacts: [ARTIFACT] }), version: 2 };

    expect(() => contracts.envelopeOf(message)).toThrow(InvalidMessageError);
  });
});

function archiveEvent(type: string, payload: Record<string, unknown>) {
  return {
    messageId: "m-1",
    correlationId: "archive-1",
    type,
    version: 1,
    occurredAt: "2026-11-01T12:00:00Z",
    payload: { archiveId: "archive-1", ...payload },
  };
}

describe("publication contracts", () => {
  test("an ArchivePublicationDecided event yields its decision version and package digest", () => {
    const contracts = new Contracts();
    const message = archiveEvent("ArchivePublicationDecided", { decisionVersion: 2, packageDigest: "sha256:p" });

    const event = contracts.parseArchiveFact("ArchivePublicationDecided", message);

    expect(event).toEqual({ messageId: "m-1", archiveId: "archive-1", decisionVersion: 2, packageDigest: "sha256:p" });
  });

  test("an ArchivePublished event without a package digest is rejected", () => {
    const contracts = new Contracts();
    const message = archiveEvent("ArchivePublished", { decisionVersion: 2 });

    expect(() => contracts.parseArchiveFact("ArchivePublished", message)).toThrow(InvalidMessageError);
  });

  test("an ArchiveCompensationDecided event yields its decision version", () => {
    const contracts = new Contracts();
    const message = archiveEvent("ArchiveCompensationDecided", { decisionVersion: 3, reasonCode: "SEED_FAILED" });

    const event = contracts.parseCompensation(message);

    expect(event).toMatchObject({ archiveId: "archive-1", decisionVersion: 3, reasonCode: "SEED_FAILED" });
  });

  test("the emitted SearchCompensated acknowledgment matches its published schema", () => {
    const contracts = new Contracts();
    const message = archiveEvent("SearchCompensated", { decisionVersion: 3 });

    expect(() => {
      contracts.assertOutgoing("SearchCompensated", message);
    }).not.toThrow();
  });
});
