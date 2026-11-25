import type { CompensationPublisher } from "../ports/compensation-publisher.js";
import type { Outbox } from "../ports/outbox.js";
import type { SearchDocumentWriter } from "../ports/search-index.js";

const OUTBOX_LEASE_SECONDS = 30;

/** Publishes one durable compensation acknowledgement after staged documents are gone. */
async function dispatchCompensationOutbox(
  outbox: Outbox,
  documentWriter: SearchDocumentWriter,
  publisher: CompensationPublisher,
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

export { dispatchCompensationOutbox };
