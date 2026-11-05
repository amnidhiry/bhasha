import { useCallback, useEffect, useState } from "preact/hooks";
import { api, type Progress as P } from "../api";
import { HandwritingProgress } from "../components/HandwritingProgress";
import { ModelSettings } from "../components/ModelSettings";
import { SchedulingCard } from "../components/SchedulingCard";
import { VoiceCard } from "../components/VoiceCard";
import { toast } from "../components/Toast";
import { num, pct } from "../format";
import { setSettings, useSettings } from "../settings";

export function Progress() {
  const [p, setP] = useState<P | null>(null);
  const [error, setError] = useState<string | null>(null);
  const settings = useSettings();
  const load = useCallback(() => api.progress().then(setP).catch((e) => setError(e.message)), []);
  useEffect(() => void load(), [load]);

  async function markLevel(level: string, known: boolean) {
    const tag = `${p!.hsk_version}:${level}`;
    const label = level === "7" ? "HSK 7–9" : `HSK ${level}`;
    if (known && !confirm(`Mark every ${label} word as known? Use this only for words you learned elsewhere.`)) return;
    await api.markLevel(tag, known ? "known" : "clear");
    toast(known ? `${label} marked known` : `${label} marks cleared`);
    void load();
  }

  if (error) return <main class="page"><p class="error">{error}</p></main>;
  if (!p) return <main class="page"><p class="muted">Loading…</p></main>;

  // Levels are cumulative; show each level's own band within the bar.
  return (
    <main class="page">
      <header class="page-head"><h1>Progress</h1></header>

      <section class="stats">
        <div class="stat card"><span class="stat-n">{num(p.known_words)}</span><span class="muted">words known</span></div>
        <div class="stat card"><span class="stat-n">{num(p.known_characters)}</span><span class="muted">characters</span></div>
        <div class="stat card"><span class="stat-n">{num(p.characters_read)}</span><span class="muted">characters read</span></div>
        <div class="stat card"><span class="stat-n">{num(p.texts_finished)}</span><span class="muted">texts finished</span></div>
      </section>

      <section class="card">
        <h2>HSK 3.0 coverage</h2>
        <p class="muted small">Cumulative words known at each level, November 2025 syllabus.</p>
        <ul class="levels">
          {p.hsk_cumulative.map((l) => (
            <li key={l.level} class="level">
              <span class="level-name">{l.level === "7" ? "7–9" : l.level}</span>
              <span class="meter" role="meter" aria-valuemin={0} aria-valuemax={l.words} aria-valuenow={l.known}
                aria-label={`HSK ${l.level}`}>
                <span style={{ width: `${(l.coverage ?? 0) * 100}%` }} />
              </span>
              <span class="level-num">{num(l.known)} / {num(l.words)}</span>
              <span class="level-pct muted">{pct(l.coverage)}</span>
            </li>
          ))}
        </ul>
        {p.hsk_cumulative.length === 0 && <p class="muted">No HSK data imported yet. Run ops/import-data.sh.</p>}
      </section>

      <HandwritingProgress />

      <details class="card">
        <summary>Already know some Chinese?</summary>
        <p class="muted small">
          Mark a whole level as known so texts are rated correctly. Words you mark skip review; you can undo it.
        </p>
        <div class="row wrap">
          {p.hsk_cumulative.slice(0, 4).map((l) => (
            <span key={l.level} class="pair">
              <button class="btn" onClick={() => markLevel(l.level, true)}>HSK {l.level} known</button>
              <button class="btn quiet" onClick={() => markLevel(l.level, false)} aria-label={`Undo HSK ${l.level}`}>undo</button>
            </span>
          ))}
        </div>
      </details>

      <SchedulingCard />

      <VoiceCard />

      <ModelSettings />

      <section class="card">
        <h2>Display</h2>
        <label class="toggle">
          <input type="checkbox" checked={settings.toneColors}
            onChange={(e) => setSettings({ toneColors: e.currentTarget.checked })} />
          <span>Color pinyin by tone</span>
        </label>
        <p class="muted small tone-legend">
          <span class="pinyin toned"><span class="t1">mā 1</span> <span class="t2">má 2</span> <span class="t3">mǎ 3</span> <span class="t4">mà 4</span> <span class="t5">ma neutral</span></span>
        </p>
      </section>
    </main>
  );
}
