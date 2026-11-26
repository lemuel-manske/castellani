import type { EventsPublisher } from "../ports/events-publisher.js";
import type { Outbox } from "../ports/outbox.js";
import type { SearchDocumentWriter } from "../ports/search-index.js";

const OUTBOX_LEASE_SECONDS = 30;

/** Publishes one durable outbox event after any required staged-document cleanup. */
async function dispatchOutbox(
  outbox: Outbox,
  documentWriter: SearchDocumentWriter,
  publisher: EventsPublisher,
): Promise<boolean> {
  const message = await outbox.claim(OUTBOX_LEASE_SECONDS);

  if (message === undefined) {
    return false;
  }

  if (message.cleanupRequired) {
    await documentWriter.deleteArchive(message.correlationId);

    const stillOwned = await outbox.completeCleanup(message);

    if (!stillOwned) {
      return true;
    }
  }

  await publisher.publish(message);
  await outbox.confirm(message);

  return true;
}

export { dispatchOutbox };
