import { dispatchOutbox } from "../application/dispatchOutbox.js";

import type { EventsPublisher } from "../ports/events-publisher.js";
import type { Outbox } from "../ports/outbox.js";
import type { SearchDocumentWriter } from "../ports/search-index.js";

import { delay } from "./delay.js";

const DISPATCH_INTERVAL_MILLISECONDS = 500;
const DISPATCH_ERROR_DELAY_MILLISECONDS = 2000;

/** Keeps draining durable outbox events until shutdown. */
async function startOutboxWorker(
  signal: AbortSignal,
  outbox: Outbox,
  documentWriter: SearchDocumentWriter,
  publisher: EventsPublisher,
): Promise<void> {
  while (!signal.aborted) {
    try {
      const dispatched = await dispatchOutbox(
        outbox,
        documentWriter,
        publisher,
      );

      if (!dispatched) {
        await delay(signal, DISPATCH_INTERVAL_MILLISECONDS);
      }
    } catch (error) {
      console.error("Search outbox dispatch failed", error);

      await delay(signal, DISPATCH_ERROR_DELAY_MILLISECONDS);
    }
  }
}

export { startOutboxWorker };
