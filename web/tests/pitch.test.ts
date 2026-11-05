// node --test web/tests/pitch.test.ts  (Node 22 strips the types)
import assert from "node:assert/strict";
import { test } from "node:test";
import { classify, contour, track, yin } from "../src/pitch.ts";

const SR = 16000;

function voice(freq: (t: number) => number, seconds = 0.6): Float32Array {
  // A voice-like signal: fundamental plus two harmonics.
  const n = Math.floor(seconds * SR), out = new Float32Array(n);
  let phase = 0;
  for (let i = 0; i < n; i++) {
    phase += (2 * Math.PI * freq(i / n)) / SR;
    out[i] = 0.5 * Math.sin(phase) + 0.25 * Math.sin(2 * phase) + 0.12 * Math.sin(3 * phase);
  }
  return out;
}

const lerp = (pts: [number, number][]) => (t: number) => {
  for (let i = 1; i < pts.length; i++) if (t <= pts[i][0]) {
    const [t0, f0] = pts[i - 1], [t1, f1] = pts[i];
    return f0 + ((f1 - f0) * (t - t0)) / (t1 - t0);
  }
  return pts[pts.length - 1][1];
};

test("yin finds the fundamental within 1%", () => {
  for (const f of [110, 220, 330]) {
    const est = yin(voice(() => f, 0.05).subarray(0, 640), SR)!;
    assert.ok(Math.abs(est - f) / f < 0.01, `${f} -> ${est}`);
  }
});

test("silence is unvoiced", () => {
  assert.equal(yin(new Float32Array(640), SR), null);
});

const guess = (f: (t: number) => number) => classify(contour(track(voice(f), SR))).tone;

test("tone 1: level", () => assert.equal(guess(() => 240), 1));
test("tone 2: rising", () => assert.equal(guess(lerp([[0, 190], [1, 270]])), 2));
test("tone 3: dipping", () => assert.equal(guess(lerp([[0, 190], [0.5, 150], [1, 220]])), 3));
// Chao 214 in semitones from a 160 Hz floor: 2 -> 1 -> 4 (the textbook isolated third tone).
const chao = (l: number) => 160 * 2 ** ((2.2 * (l - 1)) / 12);
test("tone 3: textbook 214, a short dip then a big rise", () =>
  assert.equal(guess(lerp([[0, chao(2)], [0.33, chao(1)], [1, chao(4)]])), 3));
test("tone 2 with a small early dip is still tone 2", () =>
  assert.equal(guess(lerp([[0, chao(3)], [0.12, chao(2.7)], [1, chao(5)]])), 2));
test("tone 4: falling", () => assert.equal(guess(lerp([[0, 290], [1, 160]])), 4));
test("low male voice falling still reads as tone 4", () => assert.equal(guess(lerp([[0, 140], [1, 85]])), 4));
