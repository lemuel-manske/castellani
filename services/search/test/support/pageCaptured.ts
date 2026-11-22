import { createCapturedPageFixture } from "./fixtures.js";

const EXPECTED_VERSION = 1;

function createPageCapturedEvent(messageId: string) {
  return {
    ...createCapturedPageFixture("integration-snapshot").event,
    messageId,
    type: "PageCaptured",
    version: EXPECTED_VERSION,
  };
}

export { createPageCapturedEvent };
