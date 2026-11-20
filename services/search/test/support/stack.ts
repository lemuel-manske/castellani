import { PutObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { type ChannelModel, connect } from "amqplib";
import { afterAll } from "vitest";

import type { ArtifactRef } from "../../src/indexing/model.js";
import { DEAD_QUEUE } from "../../src/messaging/consumer.js";
import { artifactRefFor, buildWarc } from "./warc.js";

/**
 * Fixtures for the running Compose stack. Configure with:
 * SEARCH_TEST_URL, SEARCH_TEST_AWS_ENDPOINT, SEARCH_TEST_RABBITMQ_URL.
 */
const env = {
  searchUrl: process.env.SEARCH_TEST_URL ?? "http://search:8082",
  awsEndpoint: process.env.SEARCH_TEST_AWS_ENDPOINT ?? "http://ministack:4566",
  rabbitUrl: process.env.SEARCH_TEST_RABBITMQ_URL ?? "amqp://castellani:local-development-only@rabbitmq:5672/",
  exchange: "castellani.events",
  bucket: "castellani-archive-artifacts",
};

const s3 = new S3Client({
  region: "us-east-1",
  endpoint: env.awsEndpoint,
  forcePathStyle: true,
  credentials: { accessKeyId: "test", secretAccessKey: "test" },
});

let broker: ChannelModel | undefined;

afterAll(async () => {
  await broker?.close();
  s3.destroy();
});

/** Stores a single-page WARC in the artifacts bucket, as Capture would. */
export async function storeCapturedPage(url: string, html: string): Promise<ArtifactRef> {
  const warc = await buildWarc([{ url, body: html }]);
  const key = `test/${crypto.randomUUID()}.warc.gz`;

  await s3.send(new PutObjectCommand({ Bucket: env.bucket, Key: key, Body: warc }));

  return { ...artifactRefFor(warc, key), bucket: env.bucket };
}

/** Publishes an event to the shared exchange with confirms, routed by type. */
export async function publish(message: Record<string, unknown>): Promise<void> {
  broker ??= await connect(env.rabbitUrl);
  const channel = await broker.createConfirmChannel();

  channel.publish(env.exchange, String(message.type), Buffer.from(JSON.stringify(message)), {
    persistent: true,
    contentType: "application/json",
    messageId: String(message.messageId),
  });
  await channel.waitForConfirms();
  await channel.close();
}

/** Raw bytes publication, for messages that are not valid JSON. */
export async function publishRaw(type: string, body: string, messageId: string): Promise<void> {
  broker ??= await connect(env.rabbitUrl);
  const channel = await broker.createConfirmChannel();

  channel.publish(env.exchange, type, Buffer.from(body), { persistent: true, messageId });
  await channel.waitForConfirms();
  await channel.close();
}

/** Waits until a message with `messageId` reaches Search's dead-letter queue. */
export async function deadLettered(messageId: string, timeoutMs = 15_000): Promise<boolean> {
  broker ??= await connect(env.rabbitUrl);
  const channel = await broker.createChannel();
  const deadline = Date.now() + timeoutMs;

  try {
    while (Date.now() < deadline) {
      const message = await channel.get(DEAD_QUEUE, { noAck: false });

      if (message === false) {
        await sleep(250);
        continue;
      }

      const found = message.properties.messageId === messageId;

      // Leave unrelated dead letters in place for whoever owns them.
      channel.nack(message, false, !found);

      if (found) {
        return true;
      }
    }

    return false;
  } finally {
    await channel.close();
  }
}

export type SearchResponse = {
  status: number;
  body: { results: Record<string, unknown>[]; nextCursor: string | null };
};

export async function search(params: Record<string, string>): Promise<SearchResponse> {
  const response = await fetch(`${env.searchUrl}/search?${new URLSearchParams(params).toString()}`);

  return { status: response.status, body: (await response.json()) as SearchResponse["body"] };
}

/** Polls `search` until `predicate` holds, failing after `timeoutMs`. */
export async function searchUntil(
  params: Record<string, string>,
  predicate: (response: SearchResponse) => boolean,
  timeoutMs = 20_000,
): Promise<SearchResponse> {
  const deadline = Date.now() + timeoutMs;
  let last = await search(params);

  while (!predicate(last)) {
    if (Date.now() > deadline) {
      throw new Error(`search condition not met within ${timeoutMs}ms; last response ${JSON.stringify(last)}`);
    }

    await sleep(250);
    last = await search(params);
  }

  return last;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
