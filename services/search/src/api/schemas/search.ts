interface SearchQuery {
  q: string;
  collectionId?: string;
  archiveId?: string;
  snapshotId?: string;
  capturedFrom?: string;
  capturedTo?: string;
  limit?: number;
  cursor?: string;
}

const searchQuerySchema = {
  type: "object",
  additionalProperties: false,
  required: ["q"],
  properties: {
    q: { type: "string", minLength: 1, maxLength: 500 },
    collectionId: { type: "string" },
    archiveId: { type: "string" },
    snapshotId: { type: "string" },
    capturedFrom: { type: "string", format: "date-time" },
    capturedTo: { type: "string", format: "date-time" },
    limit: { type: "integer", minimum: 1, maximum: 100 },
    cursor: {
      type: "string",
      maxLength: 2048,
      pattern: "^[A-Za-z0-9_-]+$",
    },
  },
} as const;

export { searchQuerySchema };
export type { SearchQuery };
