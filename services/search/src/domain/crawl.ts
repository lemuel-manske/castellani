import type { ArtifactReference } from "../ports/artifacts.js";

interface CompletionCrawl {
  archiveId: string;
  manifestDigest: string;
  manifest: ArtifactReference;
  seedSucceeded: boolean;
  capturedCount: number;
  failedCount: number;
}

export type { CompletionCrawl };
