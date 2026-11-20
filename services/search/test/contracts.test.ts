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
