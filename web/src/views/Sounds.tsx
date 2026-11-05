import { useEffect, useState } from "preact/hooks";
import { api, type Bootcamp, type DrillItem } from "../api";
import { play } from "../audio";
import { PlayIcon } from "../components/LookupSheet";
import { SayIt } from "../components/SayIt";
import { toast } from "../components/Toast";
import { pct } from "../format";
import { go } from "../router";

/** A tone's pitch shape on the five-level Chao scale. */
function ToneShape({ chao }: { chao: number[] }) {
  const W = 64, H = 40;
  const pts = chao.map((v, i) => `${(i / Math.max(1, chao.length - 1)) * (W - 8) + 4},${H - 4 - ((v - 1) / 4) * (H - 8)}`);
  return (
    <svg class="tone-shape" viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      {[1, 2, 3, 4, 5].map((l) => <line key={l} x1="0" x2={W} y1={H - 4 - ((l - 1) / 4) * (H - 8)} y2={H - 4 - ((l - 1) / 4) * (H - 8)} />)}
      <polyline points={pts.join(" ")} />
    </svg>
  );
}

const fake = (key: string, char: string) => ({ key, char, text: char, speakers: [] as string[] });

export function Sounds() {
  const [b, setB] = useState<Bootcamp | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => void api.bootcamp().then(setB).catch((e) => setError(e.message)), []);
  if (error) return <main class="page"><p class="error">{error}</p></main>;
  if (!b) return <main class="page"><p class="muted">Loading…</p></main>;

  const playKey = (key: string, char: string) => play(b.recorded_audio ? { ...fake(key, char), speakers: ["FV1", "FV2", "FV3", "MV1", "MV2", "MV3"] } : fake(key, char));
  const core = b.drills.filter((d) => !d.group);
  const contrasts = b.drills.filter((d) => d.group === "contrast");

  return (
    <main class="page sounds">
      <header class="page-head"><h1>Sounds</h1></header>
      <p class="muted">
        Weeks 1–2: learn to hear and say tones and the sounds English doesn't have, before learning many words.
        {!b.recorded_audio && " Audio uses your device's Mandarin voice; import Tone Perfect for six recorded voices."}
      </p>

      <section class="card">
        <h2>1 · The four tones</h2>
        <div class="tone-examples" lang="zh-CN">
          {b.tone_examples.map((e) => (
            <button key={e.key} class="chip-btn" onClick={() => playKey(e.key, e.char)}>{e.label} {e.char}</button>
          ))}
        </div>
        <ol class="tone-list">
          {b.tones.map((t) => {
            const ex = b.tone_examples.find((e) => e.key === `ma${t.tone}`);
            return (
              <li key={t.tone} class="tone-card">
                <div class="tone-head">
                  <ToneShape chao={t.chao} />
                  <div>
                    <h3>{t.name} <span class="muted">{t.mark}</span></h3>
                    <p class="small muted">Pitch {t.chao.join("")} on a 1–5 scale</p>
                  </div>
                  {ex && <button class="icon-btn" aria-label={`Play ${ex.label}`} onClick={() => playKey(ex.key, ex.char)}><PlayIcon /></button>}
                </div>
                <p>{t.how}</p>
                <p class="small"><b>For English speakers:</b> {t.english}</p>
                <p class="small muted"><b>Watch out:</b> {t.pitfall}</p>
                {t.tone <= 4 && ex && <SayIt tone={t.tone} chao={t.chao} label={ex.label} />}
              </li>
            );
          })}
        </ol>
      </section>

      <section class="card">
        <h2>2 · Initials: sounds that aren't English</h2>
        {b.initial_groups.map((g) => (
          <div key={g.id} class="initial-group">
            <div class="initials">
              {g.initials.map((i) => <span key={i} class="initial">{i}</span>)}
              <span class="spacer" />
              {g.audio.map((a) => (
                <button key={a.key} class="chip-btn" lang="zh-CN" onClick={() => playKey(a.key, a.char)}>{a.label}</button>
              ))}
            </div>
            <p class="small">{g.tip}</p>
          </div>
        ))}
      </section>

      <section class="card">
        <h2>3 · Finals and spelling</h2>
        {b.final_notes.map((n) => (
          <div key={n.id} class="final-note"><h3>{n.title}</h3><p class="small">{n.body}</p></div>
        ))}
      </section>

      <section class="card">
        <h2>4 · Drills</h2>
        <p class="muted small">Mastered at {pct(b.mastery.accuracy)} over your last {b.mastery.window}. Weak spots come up more often.</p>
        <DrillList drills={core} />
        <h3 class="sub-h">Sounds English speakers mix up</h3>
        <DrillList drills={contrasts} />
        <p class="muted small">
          Tone accuracy: {[1, 2, 3, 4].map((t) => `${t}: ${pct(b.tone_accuracy[String(t)])}`).join(" · ")}
        </p>
      </section>
    </main>
  );
}

function DrillList({ drills }: { drills: Bootcamp["drills"] }) {
  return (
    <ul class="drill-list">
      {drills.map((d) => (
        <li key={d.id}>
          <a class="drill-row" href={`#/sounds/drill/${encodeURIComponent(d.id)}`}>
            <span class="drill-title">{d.title}{d.mastered && <span class="chip status-known">mastered</span>}</span>
            <span class="meter small-meter"><span style={{ width: `${(d.accuracy ?? 0) * 100}%` }} /></span>
            <span class="muted small">{d.attempts ? pct(d.accuracy) : "new"}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

const TONES_FIRST = ["1", "2", "3", "4"];
const TONES_SECOND = ["1", "2", "3", "4", "5"];

export function Drill({ drill }: { drill: string }) {
  const [items, setItems] = useState<DrillItem[] | null>(null);
  const [i, setI] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [pair, setPair] = useState<[string | null, string | null]>([null, null]);
  const [score, setScore] = useState(0);

  useEffect(() => {
    api.drill(drill).then(setItems).catch((e) => toast(e.message));
  }, [drill]);
  const item = items?.[i];
  useEffect(() => {
    setPicked(null);
    setPair([null, null]);
    if (item) setTimeout(() => play(item.audio), 250);
  }, [item?.item, i]);

  if (!items) return <main class="page"><p class="muted">Loading…</p></main>;
  if (!items.length) return <main class="page"><p class="muted">No items yet: import the HSK data first.</p><a href="#/sounds">Back</a></main>;

  if (!item) {
    return (
      <main class="page">
        <section class="empty card">
          <p class="empty-glyph" lang="zh-CN" aria-hidden="true">{score >= items.length * 0.85 ? "好" : "练"}</p>
          <h2>{score} / {items.length}</h2>
          <p class="muted">{score >= items.length * 0.85 ? "Solid. Keep the streak going on another day; mastery counts your last 20." : "Again later today, or tomorrow. Short, frequent rounds work best."}</p>
          <div class="row">
            <button class="btn primary" onClick={() => { setItems(null); setI(0); setScore(0); api.drill(drill).then(setItems); }}>Another round</button>
            <a class="btn" href="#/sounds">Back to Sounds</a>
          </div>
        </section>
      </main>
    );
  }

  const answer = (value: string) => {
    if (picked) return;
    const correct = value === item.answer;
    setPicked(value);
    if (correct) setScore((s) => s + 1);
    void api.drillAttempt({ drill: item.drill, item: item.item, answer: value, correct }).catch(() => {});
  };
  const twoTone = item.options === null;
  const title = drill === "tone" ? "Which tone?" : drill === "pair" ? "Which tones?" : drill === "sandhi" ? "How is it said?" : item.prompt;

  return (
    <main class="page drill">
      <header class="rv-top">
        <a href="#/sounds" class="back" aria-label="Back to Sounds">‹</a>
        <span class="muted">{i + 1} / {items.length} · {score} right</span>
      </header>
      <section class="card drill-card">
        <p class="rv-prompt muted">{title}</p>
        {drill !== "sandhi" && !drill.startsWith("contrast:") && <p class="drill-prompt">{item.prompt}</p>}
        {drill === "sandhi" && <p class="drill-prompt" lang="zh-CN">{item.prompt}</p>}
        <button class="rv-listen" onClick={() => play(item.audio)} aria-label="Play again"><PlayIcon /></button>

        {!twoTone ? (
          <div class={`drill-options n${item.options!.length}`}>
            {item.options!.map((o) => (
              <button key={o.value}
                class={`opt ${picked ? (o.value === item.answer ? "right" : o.value === picked ? "wrong" : "") : ""}`}
                onClick={() => (picked && o.audio ? play(o.audio) : answer(o.value))}>
                {o.label}
                {picked && o.audio && <small>tap to hear</small>}
              </button>
            ))}
          </div>
        ) : (
          <div class="pair-pick">
            {[TONES_FIRST, TONES_SECOND].map((opts, slot) => (
              <div key={slot} class="pair-row" role="radiogroup" aria-label={`Syllable ${slot + 1}`}>
                <span class="muted small">{slot ? "2nd" : "1st"}</span>
                {opts.map((t) => (
                  <button key={t} role="radio" aria-checked={pair[slot] === t} disabled={!!picked}
                    class={`opt tone-opt ${pair[slot] === t ? "on" : ""} ${picked ? (item.answer[slot] === t ? "right" : pair[slot] === t ? "wrong" : "") : ""}`}
                    onClick={() => setPair(slot ? [pair[0], t] : [t, pair[1]])}>
                    {t === "5" ? "·" : t}
                  </button>
                ))}
              </div>
            ))}
            {!picked && (
              <button class="btn primary" disabled={!pair[0] || !pair[1]} onClick={() => answer(`${pair[0]}${pair[1]}`)}>Check</button>
            )}
          </div>
        )}

        {picked && (
          <div class="drill-feedback">
            <p class={picked === item.answer ? "ok" : "error"}>
              {picked === item.answer ? "Right." : "Not quite."} <span lang="zh-CN">{item.reveal}</span>
            </p>
            <button class="btn primary" onClick={() => setI(i + 1)} autoFocus>Next</button>
          </div>
        )}
      </section>
    </main>
  );
}
