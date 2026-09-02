/// <reference types="vitest/config" />
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const OUT_DIR = "../src/rcm_agent/console/static";

/**
 * Files whose contents decide what the bundle contains.
 *
 * Not the tests: changing an assertion cannot change the built page. Paths are
 * POSIX-relative to `console/` so the digest is the same on any machine, and
 * sorted so it does not depend on how the filesystem hands them back.
 */
function bundleInputs(): string[] {
  const sources = readdirSync("src", { recursive: true, encoding: "utf8" })
    .map((name) => `src/${name.split("\\").join("/")}`)
    .filter((path) => statSync(path).isFile());
  return [
    ...sources,
    "index.html",
    "package.json",
    "tsconfig.json",
    "vite.config.ts",
  ].sort();
}

/**
 * Stamp the built output with a digest of what produced it.
 *
 * The bundle is committed, so it can drift from its source and every test still
 * passes: the TypeScript tests exercise the source, the Python tests exercise
 * the output, and nothing has ever tied the two together. This is that tie -
 * `tests/test_console.py` recomputes this digest and fails when the committed
 * bundle was built from something other than the committed source.
 */
function stampSource(): Plugin {
  return {
    name: "stamp-source",
    closeBundle() {
      const hash = createHash("sha256");
      for (const path of bundleInputs()) {
        hash.update(path);
        hash.update("\0");
        hash.update(readFileSync(path));
      }
      writeFileSync(join(OUT_DIR, "source-digest.txt"), `${hash.digest("hex")}\n`);
    },
  };
}

export default defineConfig({
  plugins: [react(), stampSource()],
  // Relative, so the bundle does not care what path it is served from. The
  // hosted console and a local `rcm-agent console` are the same files.
  base: "./",
  build: {
    // Into the Python package, because that is what ships. A reviewer runs
    // `uv run` and never learns this directory was built by anything.
    outDir: OUT_DIR,
    emptyOutDir: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
