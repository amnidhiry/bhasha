// Test driver: runs web/src/scheduler.ts from a given FSRS state. Used by backend/tests/test_fsrs_parity.py.
import { makeScheduler, review } from "../src/scheduler.ts";
const [params, start, steps] = process.argv.slice(2).map((a) => JSON.parse(a));
const s = await makeScheduler(params);
let f = start;
let now = new Date(f.last_review ?? "2026-11-01T09:00:00Z");
const out = [];
for (const [g, mins] of steps) {
  now = new Date(now.getTime() + mins * 60000);
  f = review(s, f, 7, g, now);
  out.push(f);
}
console.log(JSON.stringify(out));
