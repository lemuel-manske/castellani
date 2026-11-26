import { PAGE_CAPTURED_EVENT } from "../../src/domain/index.js";
import { createCapturedPageFixture } from "./fixtures.js";

const EXPECTED_VERSION = 1;

function createPageCapturedEvent(messageId: string) {
  return {
    ...createCapturedPageFixture("integration-snapshot").event,
    messageId,
    type: PAGE_CAPTURED_EVENT,
    version: EXPECTED_VERSION,
  };
}

export { createPageCapturedEvent };
