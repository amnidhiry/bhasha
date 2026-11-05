import { Fragment } from "preact";
import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";
import { api, type TextDoc, type Tok } from "../api";
import { LookupSheet, PlayIcon, type LookupTarget } from "../components/LookupSheet";
import { toast } from "../components/Toast";
import { go } from "../router";
import { setSettings, useSettings, type PinyinMode } from "../settings";
import { canSpeak, speak } from "../speech";
import { pct } from "../format";

function Word({ tok, mode, onTap }: { tok: Tok; mode: PinyinMode; onTap: (t: Tok) => void }) {
  if (tok.kind === "punct" || tok.kind === "other" || tok.kind === "number") {
    return <span class="tok-plain">{tok.surface}</span>;
  }
  // Names carry no learner status but beginners still need their reading.
  const showPinyin = mode === "all" || (mode === "unknown" && (tok.show_reading || tok.kind === "proper"));
  const status = tok.kind === "proper" ? "proper" : (tok.status ?? "new");
  return (
    <button class={`tok s-${status}`} onClick={() => onTap(tok)}
      aria-label={`${tok.surface}, ${status}`}>
      {tok.syllables.length && showPinyin
        ? tok.syllables.map((s, i) => (
            <ruby key={i}>
              {s.text}
              <rt>{s.surface_display}</rt>
            </ruby>
          ))
        : tok.surface}
    </button>
  );
}

const NO_LINE_START = /^[。，、；：！？）」』》〉】”’…—,.;:!?)\]]+$/;

/** Keep closing punctuation on the same line as the word before it (kinsoku). */
function glue(tokens: Tok[]): Tok[][] {
  const out: Tok[][] = [];
  for (const t of tokens) {
    if (out.length && t.kind === "punct" && NO_LINE_START.test(t.surface.trim())) out[out.length - 1].push(t);
    else out.push([t]);
  }
  return out;
}

export function Reader({ id, onReviewsChanged }: { id: number; onReviewsChanged: () => void }) {
  const [doc, setDoc] = useState<TextDoc | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<LookupTarget | null>(null);
  const looked = useRef(new Set<number>());
  const [showEn, setShowEn] = useState(false);
  const [flagged, setFlagged] = useState<Set<number>>(new Set());
  const settings = useSettings();

  const load = useCallback(() => {
    api.text(id).then(setDoc).catch((e) => setError(e.message));
  }, [id]);
  useEffect(load, [load]);

  const sentences = useMemo(() => {
    const out: Tok[][] = [];
    for (const t of doc?.tokens ?? []) (out[t.sentence_index] ??= []).push(t);
    return out.filter(Boolean);
  }, [doc]);

  const onTap = (tok: Tok) => {
    const sentence = sentences.find((s) => s.includes(tok))?.map((t) => t.surface).join("").trim() ?? "";
    // Log only the first tap per word per visit: re-tapping to hear it again isn't a new failure.
    const log = tok.unit_id != null && !looked.current.has(tok.unit_id);
    if (tok.unit_id != null) looked.current.add(tok.unit_id);
    setTarget({ surface: tok.surface, unitId: tok.unit_id, status: tok.status, syllables: tok.syllables,
      sentence, textId: id, log });
  };

  async function finish() {
    try {
      const r = await api.finish(id);
      toast(`Logged ${r.exposures} words · ${r.characters_read} characters read`);
      go("#/");
    } catch (e) {
      toast(`Couldn't save: ${(e as Error).message}`);
    }
  }

  const meta = doc?.meta ?? {};
  const map = meta.sentence_map ?? [];
  const genSentences = meta.sentences ?? [];
  // Show a translation after the last reader sentence that belongs to each generated sentence.
  const translationAfter = (readerIdx: number): number | null => {
    const g = map[readerIdx];
    if (g == null || map[readerIdx + 1] === g) return null;
    return g;
  };
  const isFlagged = (g: number) => flagged.has(g) || (meta.flags ?? []).some((f) => f.sentence === g);
  async function flag(g: number) {
    try {
      await api.flag(id, g);
      setFlagged(new Set([...flagged, g]));
      toast("Flagged as unnatural. It won't be reused.");
    } catch (e) {
      toast(`Couldn't save: ${(e as Error).message}`);
    }
  }

  if (error) return <main class="page"><p class="error">{error}</p><a href="#/">Back</a></main>;
  if (!doc) return <main class="page"><p class="muted">Loading…</p></main>;

  const counts = { new: 0, learning: 0 };
  const seen = new Set<number>();
  for (const t of doc.tokens) {
    if (t.kind !== "word" || t.unit_id == null || seen.has(t.unit_id)) continue;
    seen.add(t.unit_id);
    if (t.status === "new") counts.new++;
    if (t.status === "learning") counts.learning++;
  }

  return (
    <main class="page reader" style={{ "--reader-scale": settings.fontScale }}>
      <header class="reader-head">
        <a href="#/" class="back" aria-label="Back to library">‹</a>
        <div class="reader-title">
          <h1 lang="zh-CN">{doc.title}</h1>
          {meta.title_en && <p class="title-en">{meta.title_en}</p>}
          <p class="muted">
            <span class="cov">{pct(doc.coverage_now)} known</span>
            {" · "}{counts.new} new · {counts.learning} learning
          </p>
        </div>
      </header>

      <div class="reader-tools" role="toolbar" aria-label="Reading options">
        <div class="seg" role="radiogroup" aria-label="Pinyin">
          {(["unknown", "all", "none"] as const).map((m) => (
            <button key={m} role="radio" aria-checked={settings.pinyin === m} class={settings.pinyin === m ? "on" : ""}
              onClick={() => setSettings({ pinyin: m })}>
              {m === "unknown" ? "Pinyin: new" : m === "all" ? "All" : "Off"}
            </button>
          ))}
        </div>
        <div class="seg" aria-label="Text size">
          <button onClick={() => setSettings({ fontScale: Math.max(0.8, settings.fontScale - 0.1) })} aria-label="Smaller text">A−</button>
          <button onClick={() => setSettings({ fontScale: Math.min(1.6, settings.fontScale + 0.1) })} aria-label="Larger text">A+</button>
        </div>
        {genSentences.length > 0 && (
          <button class={`seg-single ${showEn ? "on" : ""}`} aria-pressed={showEn} onClick={() => setShowEn(!showEn)}>
            English
          </button>
        )}
        {canSpeak() && (
          <button class="icon-btn" aria-label="Play whole text" onClick={() => speak(doc.tokens.map((t) => t.surface).join(""))}>
            <PlayIcon />
          </button>
        )}
      </div>

      <article class="reading" lang="zh-CN">
        {sentences.map((s, i) => {
          const g = showEn ? translationAfter(s[0].sentence_index) : null;
          return (
          <Fragment key={i}>
          <span class="sentence">
            {glue(s).map((g) =>
              g.length === 1 ? (
                <Word key={g[0].position} tok={g[0]} mode={settings.pinyin} onTap={onTap} />
              ) : (
                <span class="nobr" key={g[0].position}>
                  {g.map((t) => <Word key={t.position} tok={t} mode={settings.pinyin} onTap={onTap} />)}
                </span>
              )
            )}
          </span>
          {g != null && genSentences[g] && (
            <span class="translation" lang="en">
              {genSentences[g].en}
              <button class={`flag ${isFlagged(g) ? "on" : ""}`} disabled={isFlagged(g)} onClick={() => flag(g)}
                aria-label="Flag this sentence as unnatural Chinese" title="Sounds unnatural">
                {isFlagged(g) ? "flagged" : "⚑"}
              </button>
            </span>
          )}
          </Fragment>
          );
        })}
      </article>

      {doc.provenance === "generated" && (
        <p class="gen-note muted small">
          Generated at HSK {meta.level ?? "?"}. Chinese written by a model; pinyin and glosses from local dictionaries.
          {meta.accepted_with_issues && meta.out_of_bounds?.length
            ? <> Includes words beyond your level: <span lang="zh-CN">{meta.out_of_bounds.join("、")}</span>.</>
            : null}
        </p>
      )}

      {(meta.questions?.length ?? 0) > 0 && (
        <section class="questions">
          <h2>Check yourself</h2>
          <ol>
            {meta.questions!.map((q, i) => (
              <li key={i}>
                <p class="q-zh" lang="zh-CN">{q.question_zh}</p>
                <details>
                  <summary>English and answer</summary>
                  <p class="muted">{q.question_en}</p>
                  <p>{q.answer_en}</p>
                </details>
              </li>
            ))}
          </ol>
        </section>
      )}

      <footer class="reader-foot">
        {doc.finished_at ? (
          <p class="muted">Read before. Finishing again logs another encounter with each word.</p>
        ) : (
          <p class="muted">Finishing logs that you met each word here. It never counts as a review.</p>
        )}
        <button class="btn primary wide" onClick={finish}>Finished</button>
      </footer>

      <LookupSheet target={target} onClose={() => setTarget(null)} onChanged={() => { load(); onReviewsChanged(); }} />
    </main>
  );
}
