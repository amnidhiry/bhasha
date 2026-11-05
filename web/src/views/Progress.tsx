import { useCallback, useEffect, useState } from "preact/hooks";
import { api, type Progress as P } from "../api";
import { HandwritingProgress } from "../components/HandwritingProgress";
import { ModelSettings } from "../components/ModelSettings";
import { SchedulingCard } from "../components/SchedulingCard";
import { VoiceCard } from "../components/VoiceCard";
import { toast } from "../components/Toast";
import { num, pct } from "../format";
import { adopt, has, isPinyin, lang, levelLabel, tl, type LanguageMeta } from "../lang";
import { setSettings, useSettings } from "../settings";

export function Progress() {
  const [p, setP] = useState<P | null>(null);
  const [error, setError] = useState<string | null>(null);
  const settings = useSettings();
  const L = lang();
  const fw = L.levels.name.replace(/\s*\d+(\.\d+)?$/, "") || "Level"; // "HSK 3.0" -> "HSK"
  const load = useCallback(() => api.progress().then(setP).catch((e) => setError(e.message)), []);
  useEffect(() => void load(), [load]);

  async function markLevel(level: string, known: boolean) {
    const tag = `${p!.level_version}:${level}`;
    const label = `${fw} ${levelLabel(level)}`;
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
        {p.known_characters !== undefined && (
          <div class="stat card"><span class="stat-n">{num(p.known_characters)}</span><span class="muted">characters</span></div>
        )}
        <div class="stat card"><span class="stat-n">{num(p.read)}</span><span class="muted">{p.read_unit} read</span></div>
        <div class="stat card"><span class="stat-n">{num(p.texts_finished)}</span><span class="muted">texts finished</span></div>
      </section>

      <LanguagePicker />

      {has("characters") && <a class="card ch-link-card" href="#/chars">
        <span class="ch-link-glyph" lang={tl()} aria-hidden="true">字</span>
        <span>
          <h2>Characters</h2>
          <span class="muted small">Your {num(p.known_characters ?? 0)} characters by component, stroke order, and which parts help.</span>
        </span>
        <span class="ch-link-go" aria-hidden="true">›</span>
      </a>}

      <section class="card">
        <h2>{p.framework} coverage</h2>
        <p class="muted small">Cumulative words known at each level{L.code === "zh" ? ", November 2025 syllabus" : ""}.</p>
        <ul class="levels">
          {p.level_cumulative.map((l) => (
            <li key={l.level} class="level">
              <span class="level-name">{l.label}</span>
              <span class="meter" role="meter" aria-valuemin={0} aria-valuemax={l.words} aria-valuenow={l.known}
                aria-label={`${fw} ${l.label}`}>
                <span style={{ width: `${(l.coverage ?? 0) * 100}%` }} />
              </span>
              <span class="level-num">{num(l.known)} / {num(l.words)}</span>
              <span class="level-pct muted">{pct(l.coverage)}</span>
            </li>
          ))}
        </ul>
        {p.level_cumulative.length === 0 && <p class="muted">No {fw} data imported yet. Run ops/import-data.sh.</p>}
      </section>

      {has("handwriting") && <HandwritingProgress />}

      <details class="card">
        <summary>Already know some {L.adjective}?</summary>
        <p class="muted small">
          Mark a whole level as known so texts are rated correctly. Words you mark skip review; you can undo it.
        </p>
        <div class="row wrap">
          {p.level_cumulative.slice(0, 4).map((l) => (
            <span key={l.level} class="pair">
              <button class="btn" onClick={() => markLevel(l.level, true)}>{fw} {l.label} known</button>
              <button class="btn quiet" onClick={() => markLevel(l.level, false)} aria-label={`Undo ${fw} ${l.label}`}>undo</button>
            </span>
          ))}
        </div>
      </details>

      <SchedulingCard />

      {has("tonecheck") && <VoiceCard />}

      <ModelSettings />

      {isPinyin() && <section class="card">
        <h2>Display</h2>
        <label class="toggle">
          <input type="checkbox" checked={settings.toneColors}
            onChange={(e) => setSettings({ toneColors: e.currentTarget.checked })} />
          <span>Color pinyin by tone</span>
        </label>
        <p class="muted small tone-legend">
          <span class="pinyin toned"><span class="t1">mā 1</span> <span class="t2">má 2</span> <span class="t3">mǎ 3</span> <span class="t4">mà 4</span> <span class="t5">ma neutral</span></span>
        </p>
      </section>}
    </main>
  );
}

/** Which language you're studying: shown only when more than one pack is installed. */
function LanguagePicker() {
  const [langs, setLangs] = useState<LanguageMeta[]>([]);
  useEffect(() => void api.languages().then(setLangs).catch(() => {}), []);
  if (langs.length < 2) return null;
  async function choose(code: string) {
    const me = await api.setLanguage(code);
    adopt(me.language);
    location.hash = "#/";
    location.reload();
  }
  return (
    <section class="card">
      <h2>Studying</h2>
      <div class="row wrap" role="radiogroup" aria-label="Language">
        {langs.map((l) => (
          <button key={l.code} role="radio" aria-checked={l.code === lang().code}
            class={`chip-btn ${l.code === lang().code ? "on" : ""}`} onClick={() => l.code !== lang().code && void choose(l.code)}>
            {l.name} {l.native_name && <span lang={l.bcp47}>{l.native_name}</span>}
          </button>
        ))}
      </div>
      <p class="muted small">Each language keeps its own texts, cards and progress.</p>
    </section>
  );
}
