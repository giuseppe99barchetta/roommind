import assert from "node:assert/strict";
import test from "node:test";

import { changedSettings, snapshotSettings } from "../dist/utils/settings-diff.js";

test("unchanged settings send nothing", () => {
  const payload = { a: 1, list: ["x"], nested: { b: true } };
  assert.deepEqual(changedSettings(payload, snapshotSettings(payload)), {});
});

test("only the edited keys are sent", () => {
  const saved = snapshotSettings({ a: 1, list: ["x"], vacation_until: null });
  const next = { a: 2, list: ["x"], vacation_until: null };
  assert.deepEqual(changedSettings(next, saved), { a: 2 });
});

test("list and object edits are detected", () => {
  const saved = snapshotSettings({ list: ["x"], obj: { k: 1 } });
  assert.deepEqual(changedSettings({ list: ["x", "y"], obj: { k: 1 } }, saved), { list: ["x", "y"] });
  assert.deepEqual(changedSettings({ list: ["x"], obj: { k: 2 } }, saved), { obj: { k: 2 } });
});

test("a key unknown to the snapshot is sent", () => {
  assert.deepEqual(changedSettings({ fresh: 0 }, snapshotSettings({})), { fresh: 0 });
});
