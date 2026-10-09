const SEED_PREFIX = "2026-2-speaking";

export async function drawExam(cls, num, n) {
  const data = new TextEncoder().encode(`${SEED_PREFIX}|${cls}|${num}`);
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", data));
  const first = hash[0] % n;
  let second = hash[1] % (n - 1);
  if (second >= first) second += 1;
  return [first, second];
}

export function drawPractice(n) {
  const a = new Uint32Array(1);
  crypto.getRandomValues(a);
  return a[0] % n;
}
