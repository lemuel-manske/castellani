const EXPECTED_VERSION = 1;

function createPageCapturedEvent(messageId: string) {
  return {
    messageId,
    correlationId: "integration-archive",
    type: "PageCaptured",
    version: EXPECTED_VERSION,
    occurredAt: "2026-11-22T10:00:00.000Z",
    payload: {
      archiveId: "integration-archive",
      snapshotId: "integration-snapshot",
      urlKey: "integration-url-key",
      url: "https://example.com/",
      finalUrl: "https://example.com/final",
      redirectChain: ["https://example.com/", "https://example.com/final"],
      capturedAt: "2026-11-22T10:00:00.000Z",
      contentType: "text/html",
      warcArtifacts: [
        {
          bucket: "capture-artifacts",
          key: "capture-staging/integration-archive/integration-url-key/attempt-1/integration-snapshot/page.warc.gz",
          sha256: "a".repeat(64),
          sizeBytes: 128,
          versionId: "integration-version",
        },
      ],
    },
  };
}

export { createPageCapturedEvent };
