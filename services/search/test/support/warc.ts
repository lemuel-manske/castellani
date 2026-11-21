import { createHash } from "node:crypto";

import { WARCRecord, WARCSerializer } from "warcio";

import type { ArtifactRef } from "../../src/indexing/model.js";

export type RecordedResponse = {
  url: string;
  body: string;
  status?: number;
  contentType?: string;
};

/** Builds a gzip-per-record WARC, as written by the Capture recorder. */
export async function buildWarc(responses: RecordedResponse[]): Promise<Uint8Array> {
  const chunks: Uint8Array[] = [];

  for (const response of responses) {
    const status = response.status ?? 200;

    const record = WARCRecord.create(
      {
        url: response.url,
        date: "2026-11-01T12:00:00Z",
        type: "response",
        warcVersion: "WARC/1.1",
        statusline: `HTTP/1.1 ${status} ${status === 200 ? "OK" : "Status"}`,
        httpHeaders: { "Content-Type": response.contentType ?? "text/html; charset=utf-8" },
      },
      bodyOf(response.body),
    );

    chunks.push(await WARCSerializer.serialize(record, { gzip: true }));
  }

  return Buffer.concat(chunks);
}

export function artifactRefFor(bytes: Uint8Array, key: string): ArtifactRef {
  return {
    bucket: "castellani-archive-artifacts",
    key,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    sizeBytes: bytes.byteLength,
  };
}

function* bodyOf(text: string): Generator<Uint8Array> {
  yield new TextEncoder().encode(text);
}
