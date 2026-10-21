const SEED_PREFIX = "2026-2-speaking";

// 대화문을 part별 색인 묶음으로 나눈다. part가 없으면 한 묶음이다.
export function partGroups(dialogues) {
  const groups = new Map();
  dialogues.forEach((d, i) => {
    const key = d.part ?? 0;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(i);
  });
  return [...groups.keys()].sort((a, b) => a - b).map((k) => groups.get(k));
}

// 본 평가 편 고르기. 묶음이 둘 이상이면 묶음마다 1편씩, 하나면 그 안에서 서로 다른 2편을 고른다.
// 같은 학생은 언제나 같은 편을 받는다.
export async function drawExam(cls, num, groups) {
  const data = new TextEncoder().encode(`${SEED_PREFIX}|${cls}|${num}`);
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", data));
  if (groups.length >= 2) return groups.map((g, i) => g[hash[i] % g.length]);
  const pool = groups[0], n = pool.length;
  const first = hash[0] % n;
  let second = hash[1] % (n - 1);
  if (second >= first) second += 1;
  return [pool[first], pool[second]];
}

export function drawPractice(n) {
  const a = new Uint32Array(1);
  crypto.getRandomValues(a);
  return a[0] % n;
}
