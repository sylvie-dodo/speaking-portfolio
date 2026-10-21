import { test } from "node:test";
import assert from "node:assert/strict";
import { drawExam, drawPractice, partGroups } from "../../lib/draw.js";

const parts = [1, 1, 1, 1, 1, 2, 2, 2, 3, 3].map((part) => ({ part }));

test("partGroups groups dialogue indexes by part in order", () => {
  assert.deepEqual(partGroups(parts), [[0, 1, 2, 3, 4], [5, 6, 7], [8, 9]]);
  assert.deepEqual(partGroups([{}, {}, {}]), [[0, 1, 2]]);
});

test("drawExam picks one dialogue from every part, deterministically", async () => {
  const groups = partGroups(parts);
  for (let n = 1; n <= 16; n++) {
    const a = await drawExam(1, n, groups);
    assert.deepEqual(a, await drawExam(1, n, groups));
    assert.equal(a.length, 3);
    a.forEach((pick, i) => assert.ok(groups[i].includes(pick), String(a)));
  }
});

test("drawExam covers every dialogue across students", async () => {
  const groups = partGroups(parts), seen = new Set();
  for (let n = 1; n <= 200; n++) (await drawExam(1, n, groups)).forEach((i) => seen.add(i));
  assert.equal(seen.size, 10);
});

test("drawExam without parts picks two distinct dialogues", async () => {
  const a = await drawExam(4, 12, [[0, 1, 2, 3, 4]]);
  assert.notEqual(a[0], a[1]);
  for (const i of a) assert.ok(i >= 0 && i < 5);
});

test("drawPractice in range", () => {
  for (let i = 0; i < 100; i++) { const d = drawPractice(8); assert.ok(d >= 0 && d < 8); }
});
