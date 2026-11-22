import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.integration.test.ts"],
    passWithNoTests: true,
    exclude: ["node_modules/**"],
    environment: "node",
    testTimeout: 60_000,
    hookTimeout: 30_000,
    fileParallelism: false,
  },
});
