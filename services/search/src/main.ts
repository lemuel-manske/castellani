import { SearchSettings } from "./assembly/config.js";
import { SearchRuntime } from "./assembly/runtime.js";

const runtime = new SearchRuntime(SearchSettings.fromEnvironment());

runtime.start().catch((error: unknown) => {
  console.error("Search service stopped unexpectedly", error);
  process.exitCode = 1;
});
