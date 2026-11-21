import { createHash } from "node:crypto";

export const DEFAULT_LIMIT = 25;
export const MAX_LIMIT = 100;
export const MAX_QUERY_LENGTH = 500;

const ALLOWED = new Set([
  "q",
  "collectionId",
  "archiveId",
  "snapshotId",
  "capturedFrom",
  "capturedTo",
  "limit",
  "cursor",
]);
// RFC 3339 date-time, as required by OpenAPI `format: date-time`.
const DATE_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/i;

export type SearchQuery = {
  text: string;
  collectionId?: string;
  archiveId?: string;
  snapshotId?: string;
  capturedFrom?: string;
  capturedTo?: string;
  limit: number;
  cursor?: string;
};

export class InvalidQueryError extends Error {}

/** Parses `GET /search` query parameters; rejects unknown or repeated ones. */
export function parseSearchQuery(raw: Record<string, unknown>): SearchQuery {
  const values: Record<string, string> = {};

  for (const [name, value] of Object.entries(raw)) {
    if (!ALLOWED.has(name)) {
      throw new InvalidQueryError(`unknown parameter ${name}`);
    }

    if (typeof value !== "string") {
      throw new InvalidQueryError(`parameter ${name} must be supplied once`);
    }

    values[name] = value;
  }

  const text = values.q;

  if (text === undefined || text.trim().length === 0) {
    throw new InvalidQueryError("q is required");
  }

  if (text.length > MAX_QUERY_LENGTH) {
    throw new InvalidQueryError(`q must be at most ${MAX_QUERY_LENGTH} characters`);
  }

  const query: SearchQuery = { text, limit: parseLimit(values.limit) };

  for (const name of ["collectionId", "archiveId", "snapshotId", "cursor"] as const) {
    const value = values[name];

    if (value !== undefined) {
      if (value.length === 0) {
        throw new InvalidQueryError(`${name} must not be empty`);
      }

      query[name] = value;
    }
  }

  for (const name of ["capturedFrom", "capturedTo"] as const) {
    const value = values[name];

    if (value !== undefined) {
      if (!DATE_TIME.test(value) || Number.isNaN(Date.parse(value))) {
        throw new InvalidQueryError(`${name} must be an RFC 3339 date-time`);
      }

      query[name] = value;
    }
  }

  if (query.capturedFrom && query.capturedTo && Date.parse(query.capturedFrom) > Date.parse(query.capturedTo)) {
    throw new InvalidQueryError("capturedFrom must not be after capturedTo");
  }

  return query;
}

function parseLimit(value: string | undefined): number {
  if (value === undefined) {
    return DEFAULT_LIMIT;
  }

  if (!/^\d+$/.test(value)) {
    throw new InvalidQueryError("limit must be an integer");
  }

  const limit = Number(value);

  if (limit < 1 || limit > MAX_LIMIT) {
    throw new InvalidQueryError(`limit must be between 1 and ${MAX_LIMIT}`);
  }

  return limit;
}

/**
 * Identifies the result set a cursor belongs to, so a cursor cannot be
 * replayed against a different query or filter combination.
 */
export function fingerprint(query: SearchQuery): string {
  const scope = [
    query.text,
    query.collectionId,
    query.archiveId,
    query.snapshotId,
    query.capturedFrom,
    query.capturedTo,
  ];

  return createHash("sha256").update(JSON.stringify(scope)).digest("base64url").slice(0, 16);
}
