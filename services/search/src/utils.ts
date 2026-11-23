function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readJSON(data: Uint8Array | Buffer): unknown {
  let value: unknown;

  try {
    value = JSON.parse(Buffer.from(data).toString("utf8")) as unknown;
  } catch {
    return null;
  }

  return value;
}

export { isRecord, readJSON };
