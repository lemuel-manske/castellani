import { InvalidQueryError } from "./query.js";

/** OpenSearch `search_after` values for the sort `[_score, capturedAt, snapshotId]`. */
export type SortKey = [number, number, string];

type Payload = { v: 1; f: string; a: SortKey };

/**
 * Opaque pagination cursor. It only encodes a position in a result set and is
 * never an authorization token: every page re-applies the full query.
 */
export function encodeCursor(queryFingerprint: string, after: SortKey): string {
  const payload: Payload = { v: 1, f: queryFingerprint, a: after };

  return Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
}

export function decodeCursor(cursor: string, queryFingerprint: string): SortKey {
  let payload: unknown;

  try {
    payload = JSON.parse(Buffer.from(cursor, "base64url").toString("utf8"));
  } catch {
    throw new InvalidQueryError("cursor is malformed");
  }

  if (!isPayload(payload)) {
    throw new InvalidQueryError("cursor is malformed");
  }

  if (payload.f !== queryFingerprint) {
    throw new InvalidQueryError("cursor does not belong to this query");
  }

  return payload.a;
}

function isPayload(value: unknown): value is Payload {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const { v, f, a } = value as Record<string, unknown>;

  return (
    v === 1 &&
    typeof f === "string" &&
    Array.isArray(a) &&
    a.length === 3 &&
    typeof a[0] === "number" &&
    Number.isFinite(a[0]) &&
    typeof a[1] === "number" &&
    Number.isFinite(a[1]) &&
    typeof a[2] === "string"
  );
}
