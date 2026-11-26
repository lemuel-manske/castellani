function bufferJSON(value: unknown): Buffer {
  return Buffer.from(JSON.stringify(value), "utf8");
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

export { readJSON, bufferJSON };
