import { createHash } from "node:crypto";

import {
  SEARCH_COMPENSATED_EVENT,
  type CompensationDecision,
  type SearchCompensationAck,
} from "../domain.js";

import type { OutboxEntry } from "../ports/outbox.js";

const MESSAGE_VERSION = 1;

function compensationMessageId(decision: CompensationDecision): string {
  return createHash("sha256")
    .update(`${decision.archiveId}:${decision.decisionVersion}`)
    .digest("hex");
}

function searchCompensatedEnvelope(
  messageId: string,
  payload: SearchCompensationAck,
  occurredAt: string,
): string {
  return JSON.stringify({
    messageId,
    correlationId: payload.archiveId,
    type: SEARCH_COMPENSATED_EVENT,
    version: MESSAGE_VERSION,
    occurredAt,
    payload,
  });
}

/** Builds the durable acknowledgement written with Search's compensation decision. */
function createSearchCompensatedOutboxEntry(
  decision: CompensationDecision,
  occurredAt: string = new Date().toISOString(),
): OutboxEntry {
  const messageId = compensationMessageId(decision);
  const payload = {
    archiveId: decision.archiveId,
    decisionVersion: decision.decisionVersion,
  };

  return {
    messageId,
    correlationId: decision.archiveId,
    type: SEARCH_COMPENSATED_EVENT,
    occurredAt,
    envelope: searchCompensatedEnvelope(messageId, payload, occurredAt),
    cleanupRequired: true,
  };
}

export { createSearchCompensatedOutboxEntry };
