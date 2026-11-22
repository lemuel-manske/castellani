import { defineConfig } from "vitest/config";

/** Integration tests against the running Compose stack (see test/support/stack.ts). */
export default defineConfig({
  test: {
    include: ["test/integration/**/*.integration.test.ts"],
    environment: "node",
    testTimeout: 60_000,
    hookTimeout: 30_000,
    fileParallelism: false,
  },
});
