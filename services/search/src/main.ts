import { SearchSettings } from "./config.js";
import { SearchRuntime } from "./runtime.js";

const shutdown = new AbortController();

const runtime = new SearchRuntime(SearchSettings.fromEnvironment());

process.once("SIGINT", () => {
  shutdown.abort();
});

process.once("SIGTERM", () => {
  shutdown.abort();
});

runtime.start(shutdown.signal).catch((error: unknown) => {
  console.error("Search service stopped unexpectedly", error);

  process.exitCode = 1;
});
