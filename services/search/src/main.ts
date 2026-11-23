import { SearchSettings } from "./assembly/config.js";
import { SearchRuntime } from "./assembly/runtime.js";

const runtime = new SearchRuntime(SearchSettings.fromEnvironment());
const shutdown = new AbortController();

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
