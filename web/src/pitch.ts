// Pitch tracking for the tone lab: YIN (de Cheveigné & Kawahara, 2002) on short
// frames, then a contour in semitones relative to the speaker's own median, so
// low and high voices compare alike. The tone guess is a hint, not a grade:
// the design doc says to show the contour and let you judge.

export function yin(frame: Float32Array, sampleRate: number, minF = 70, maxF = 500, threshold = 0.15): number | null {
  const maxLag = Math.min(Math.floor(sampleRate / minF), Math.floor(frame.length / 2));
  const minLag = Math.max(2, Math.floor(sampleRate / maxF));
  const d = new Float32Array(maxLag + 1);
  let energy = 0;
  for (let i = 0; i < frame.length; i++) energy += frame[i] * frame[i];
  if (energy / frame.length < 1e-6) return null; // silence
  for (let lag = 1; lag <= maxLag; lag++) {
    let sum = 0;
    for (let i = 0; i < frame.length - maxLag; i++) {
      const diff = frame[i] - frame[i + lag];
      sum += diff * diff;
    }
    d[lag] = sum;
  }
  // Cumulative mean normalized difference.
  let running = 0;
  const cmnd = new Float32Array(maxLag + 1);
  cmnd[0] = 1;
  for (let lag = 1; lag <= maxLag; lag++) {
    running += d[lag];
    cmnd[lag] = running ? (d[lag] * lag) / running : 1;
  }
  let tau = -1;
  for (let lag = minLag; lag <= maxLag; lag++) {
    if (cmnd[lag] < threshold) {
      while (lag + 1 <= maxLag && cmnd[lag + 1] < cmnd[lag]) lag++;
      tau = lag;
      break;
    }
  }
  if (tau < 0) return null; // unvoiced
  // Parabolic interpolation around tau.
  const a = cmnd[tau - 1] ?? cmnd[tau], b = cmnd[tau], c = cmnd[tau + 1] ?? cmnd[tau];
  const denom = a + c - 2 * b;
  const shift = denom ? (a - c) / (2 * denom) : 0;
  return sampleRate / (tau + shift);
}

/** F0 per 10 ms hop (null where unvoiced). */
export function track(samples: Float32Array, sampleRate: number, hopSec = 0.01, winSec = 0.04): (number | null)[] {
  const win = Math.floor(winSec * sampleRate), hop = Math.floor(hopSec * sampleRate);
  const out: (number | null)[] = [];
  for (let start = 0; start + win <= samples.length; start += hop) out.push(yin(samples.subarray(start, start + win), sampleRate));
  return out;
}

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? s[Math.floor(s.length / 2)] : 0;
};

/** The voiced stretch as semitones around its median, lightly smoothed and with
 * octave jumps (a common tracking error) folded back. */
export function contour(f0: (number | null)[]): number[] {
  // Longest run of voiced frames (one syllable).
  let best: number[] = [], cur: number[] = [];
  for (const f of [...f0, null]) {
    if (f) cur.push(f);
    else {
      if (cur.length > best.length) best = cur;
      cur = [];
    }
  }
  if (best.length < 5) return [];
  const ref = median(best);
  let st = best.map((f) => 12 * Math.log2(f / ref));
  st = st.map((v) => (v > 9 ? v - 12 : v < -9 ? v + 12 : v));
  // Median filter of width 5.
  return st.map((_, i) => median(st.slice(Math.max(0, i - 2), i + 3)));
}

export interface Guess {
  tone: 1 | 2 | 3 | 4 | null;
  reason: string;
}

/** A rough tone guess from contour shape (semitones over time). */
export function classify(c: number[]): Guess {
  if (c.length < 5) return { tone: null, reason: "Too short or too quiet to track. Try again a little louder." };
  const trim = Math.floor(c.length * 0.1);
  const x = c.slice(trim, c.length - trim || undefined);
  const k = Math.max(1, Math.floor(x.length * 0.2));
  const mean = (a: number[]) => a.reduce((s, v) => s + v, 0) / a.length;
  const start = mean(x.slice(0, k)), end = mean(x.slice(-k));
  const min = Math.min(...x), max = Math.max(...x);
  const minPos = x.indexOf(min) / (x.length - 1);
  const range = max - min;
  if (end - start <= -3) return { tone: 4, reason: "It falls steeply." };
  if (start - min >= 1.5 && end - min >= 1.5 && minPos > 0.2 && minPos < 0.85) return { tone: 3, reason: "It dips, then rises." };
  if (end - start >= 2.5) return { tone: 2, reason: "It rises." };
  if (range < 2) return { tone: 1, reason: "It stays level." };
  return { tone: null, reason: "The shape is unclear. Compare it with the dashed line." };
}

/** Target contour shape in semitones for a tone, from its Chao numbers. */
export function target(chao: number[], points = 40): number[] {
  const out: number[] = [];
  for (let i = 0; i < points; i++) {
    const t = (i / (points - 1)) * (chao.length - 1);
    const lo = Math.floor(t), hi = Math.min(chao.length - 1, lo + 1);
    const v = chao[lo] + (chao[hi] - chao[lo]) * (t - lo);
    out.push((v - 3) * 2.2);
  }
  return out;
}
