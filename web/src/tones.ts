// Tone of a numeric pinyin syllable ("hao3" -> 3, "le5" -> 5).
export function toneOf(numeric: string): number {
  const m = /([1-5])$/.exec(numeric);
  return m ? Number(m[1]) : 5;
}

/** Split a numeric reading and its marked display into per-syllable pairs. */
export function syllablePairs(numeric: string, display: string): { tone: number; text: string }[] {
  const n = numeric.split(/\s+/).filter(Boolean);
  const d = display.split(/\s+/).filter(Boolean);
  return d.map((text, i) => ({ text, tone: toneOf(n[i] ?? "") }));
}

