function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readJSON(data: string | Uint8Array | Buffer): unknown {
  let value: unknown;

  if (typeof data === "string") {
    data = Buffer.from(data, "base64url");
  }

  try {
    value = JSON.parse(Buffer.from(data).toString("utf8")) as unknown;
  } catch {
    return null;
  }

  return value;
}

export { isRecord, readJSON };
