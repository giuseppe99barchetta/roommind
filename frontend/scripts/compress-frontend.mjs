/**
 * Home Assistant's StaticPathConfig automatically prefers a sibling .gz file
 * for browsers accepting gzip. Keep it in sync with the JS on every build:
 * serving an old .gz silently displays a previous UI despite the new JS.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync, gunzipSync } from "node:zlib";

const frontendDir = resolve(fileURLToPath(new URL("..", import.meta.url)));
const jsPath = resolve(frontendDir, "../custom_components/roommind/frontend/roommind-panel.js");
const js = readFileSync(jsPath);
const compressed = gzipSync(js, { level: 9, mtime: 0 });

if (!gunzipSync(compressed).equals(js)) {
  throw new Error("The compressed RoomMind frontend failed its round-trip check");
}

writeFileSync(`${jsPath}.gz`, compressed);
console.log(`RoomMind gzip asset: ${compressed.length} bytes (source: ${js.length})`);
