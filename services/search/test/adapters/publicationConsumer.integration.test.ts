import { expect, it } from "vitest";
import {
  nextPublicationEvent,
  rabbitmq,
  setupIntegrationEnvironment,
} from "../support/integrationEnvironment.js";

setupIntegrationEnvironment("rabbitmq");

it("consumes publication decisions and replay acknowledgements from the events exchange", async () => {
  const event = {
    messageId: "publication-event-message",
    correlationId: "publication-event-archive",
    type: "ArchivePublicationDecided",
    version: 1,
    occurredAt: "2026-11-22T12:00:00.000Z",
    payload: {
      archiveId: "publication-event-archive",
      decisionVersion: 3,
      packageDigest: "sha256:package",
    },
  };
  const delivered = nextPublicationEvent();

  await rabbitmq.publishPublication(event, event.type);

  await expect(delivered).resolves.toEqual({
    type: "ArchivePublicationDecided",
    payload: event.payload,
  });
});

it("dead-letters malformed publication event envelopes", async () => {
  const deadLetter = rabbitmq.nextPublicationDeadLetter();

  await rabbitmq.publishPublication(
    { messageId: "malformed-publication-message" },
    "ArchivePublicationDecided",
  );

  const message = await deadLetter;

  expect(message.content.toString("utf8")).toBe(
    JSON.stringify({ messageId: "malformed-publication-message" }),
  );
});
