import {
  SEARCH_INDEXING_COMPLETED_EVENT,
  SEARCH_READY_EVENT,
  type IndexingCompletion,
  type SearchReadiness,
} from "../domain.js";

import type { OutboxEntry } from "../ports/outbox.js";

const MESSAGE_VERSION = 1;

function indexingCompletedMessageId(completion: IndexingCompletion): string {
  return `${completion.archiveId}:${completion.manifestDigest}`;
}

function searchReadyMessageId(readiness: SearchReadiness): string {
  return `${readiness.archiveId}:${readiness.decisionVersion}:${readiness.manifestDigest}`;
}

function eventEnvelope(
  type: string,
  messageId: string,
  correlationId: string,
  payload: object,
  occurredAt: string,
): string {
  return JSON.stringify({
    messageId,
    correlationId,
    type,
    version: MESSAGE_VERSION,
    occurredAt,
    payload,
  });
}

/** Builds the durable aggregate indexing outcome for a complete manifest. */
function createSearchIndexingCompletedOutboxEntry(
  completion: IndexingCompletion,
  occurredAt: string = new Date().toISOString(),
): OutboxEntry {
  const messageId = indexingCompletedMessageId(completion);

  return {
    messageId,
    correlationId: completion.archiveId,
    type: SEARCH_INDEXING_COMPLETED_EVENT,
    occurredAt,
    envelope: eventEnvelope(
      SEARCH_INDEXING_COMPLETED_EVENT,
      messageId,
      completion.archiveId,
      completion,
      occurredAt,
    ),
    cleanupRequired: false,
  };
}

/** Builds the durable projection-readiness acknowledgement for an authorized archive. */
function createSearchReadyOutboxEntry(
  readiness: SearchReadiness,
  occurredAt: string = new Date().toISOString(),
): OutboxEntry {
  const messageId = searchReadyMessageId(readiness);

  return {
    messageId,
    correlationId: readiness.archiveId,
    type: SEARCH_READY_EVENT,
    occurredAt,
    envelope: eventEnvelope(
      SEARCH_READY_EVENT,
      messageId,
      readiness.archiveId,
      readiness,
      occurredAt,
    ),
    cleanupRequired: false,
  };
}

export {
  createSearchIndexingCompletedOutboxEntry,
  createSearchReadyOutboxEntry,
  indexingCompletedMessageId,
  searchReadyMessageId,
};
