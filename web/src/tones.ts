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

export function levelLabel(tags: string[], version = "hsk3-2025"): string | null {
  const tag = tags.find((t) => t.startsWith(`${version}:`));
  if (!tag) return null;
  const n = tag.split(":")[1];
  return n === "7" ? "HSK 7–9" : `HSK ${n}`;
}
