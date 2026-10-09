import { test } from "node:test";
import assert from "node:assert/strict";
import { drawExam, drawPractice } from "../../lib/draw.js";

test("drawExam is deterministic and distinct", async () => {
  const a = await drawExam(1, 12, 5);
  const b = await drawExam(1, 12, 5);
  assert.deepEqual(a, b);
  assert.notEqual(a[0], a[1]);
  for (const i of a) assert.ok(i >= 0 && i < 5);
});

test("drawExam differs across students (sanity over 6 classes)", async () => {
  const seen = new Set();
  for (let c = 1; c <= 6; c++) for (let n = 1; n <= 28; n++) seen.add((await drawExam(c, n, 9)).join(","));
  assert.ok(seen.size > 20);
});

test("drawPractice in range", () => {
  for (let i = 0; i < 100; i++) { const d = drawPractice(5); assert.ok(d >= 0 && d < 5); }
});
