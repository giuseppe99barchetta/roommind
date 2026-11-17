import { defineConfig } from "vitest/config";

// Only the ported upstream TypeScript tests: test/*.test.mjs run under node --test
export default defineConfig({
  test: { include: ["src/**/*.test.ts"] },
});
