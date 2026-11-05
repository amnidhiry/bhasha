import { tl } from "../lang";
import HanziWriter from "hanzi-writer";
import { useEffect, useRef, useState } from "preact/hooks";
import {
  api,
  type CharacterPage,
  type CharactersOverview,
  type CharNote,
  type CharSummary,
  type CharWord,
  type ComponentResult,
} from "../api";
import { toast } from "../components/Toast";
import { loadChar } from "../components/WritingPad";
import { num } from "../format";
import { go } from "../router";
import { useSettings } from "../settings";
import { speak, canSpeak } from "../speech";
import { PlayIcon } from "../components/LookupSheet";

const cssColor = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#333";
const charHref = (ch: string) => `#/char/${encodeURIComponent(ch)}`;
const compHref = (c: string) => `#/chars/${encodeURIComponent(c)}`;

/** Tone number of a tone-marked syllable ("yín" -> 2), for tone colors. */
function toneOf(syl: string): number {
  const d = syl.normalize("NFD");
  if (d.includes("̄")) return 1;
  if (d.includes("́")) return 2;
  if (d.includes("̌")) return 3;
  if (d.includes("̀")) return 4;
  return 5;
}

function Marked({ syllables }: { syllables: string[] }) {
  const { toneColors } = useSettings();
  if (!syllables.length) return null;
  return (
    <span class={`pinyin ${toneColors ? "toned" : ""}`}>
      {syllables.map((s, i) => (
        <span key={i} class={`t${toneOf(s)}`}>{i > 0 ? " · " : ""}{s}</span>
      ))}
    </span>
  );
}

function Back({ fallback }: { fallback: string }) {
  return (
    <a href={fallback} class="back" aria-label="Back"
      onClick={(e) => {
        if (history.length > 1) {
          e.preventDefault();
          history.back();
        }
      }}>‹</a>
  );
}

const statusLabel = { known: "known", learning: "learning", new: "new" } as const;

function Tile({ c, via }: { c: CharSummary; via?: string | null }) {
  const opaque = c.transparency === "opaque";
  return (
    <a class={`ch-tile ch-${c.status}`} href={charHref(c.character)}
      title={`${c.character} ${c.pinyin.join(", ")}: ${c.definition ?? ""}${opaque ? " (its parts mislead)" : ""}`}>
      <span class="ch-glyph" lang={tl()}>{c.character}</span>
      <span class="ch-py">{c.pinyin[0] ?? ""}</span>
      {via && <span class="ch-via" lang={tl()}>in {via}</span>}
      {opaque && <span class="ch-dot" aria-label="parts mislead" />}
    </a>
  );
}

/** Stroke-order animation with Hanzi Writer, replayable by tapping. */
function StrokeOrder({ char }: { char: string }) {
  const host = useRef<HTMLDivElement>(null);
  const writer = useRef<HanziWriter | null>(null);
  useEffect(() => {
    const el = host.current!;
    el.innerHTML = "";
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const w = HanziWriter.create(el, char, {
      width: 180,
      height: 180,
      padding: 12,
      showOutline: true,
      showCharacter: reduce,
      strokeAnimationSpeed: 1.2,
      delayBetweenStrokes: 220,
      strokeColor: cssColor("--ink"),
      outlineColor: cssColor("--rule"),
      radicalColor: cssColor("--accent"),
      charDataLoader: loadChar,
      onLoadCharDataError: () => (el.textContent = ""),
    });
    writer.current = w;
    if (!reduce) void w.animateCharacter();
    return () => {
      writer.current = null;
      el.innerHTML = "";
    };
  }, [char]);
  return (
    <button class="ch-strokes tianzige" aria-label={`Play stroke order of ${char}`}
      onClick={() => void writer.current?.animateCharacter()}>
      <div ref={host} />
    </button>
  );
}

function Notes({ notes, transparency }: { notes: CharNote[]; transparency: CharacterPage["transparency"] }) {
  if (!notes.length) return null;
  const warn = (n: CharNote) => n.kind === "sound_misleading" || n.kind === "part_misleading";
  return (
    <section class="card">
      <h2>How the parts work</h2>
      <ul class="ch-notes">
        {notes.map((n, i) => (
          <li key={i} class={warn(n) ? "ch-note warn" : "ch-note"} lang="en">{n.text}</li>
        ))}
      </ul>
      {transparency === "opaque" && (
        <p class="muted small">
          Parts don't always help: here it's easier to learn the character as a whole, or through the words you know.
        </p>
      )}
    </section>
  );
}

function WordList({ words }: { words: CharWord[] }) {
  return (
    <ul class="ch-words">
      {words.map((w) => (
        <li key={w.unit_id}>
          <span class="ch-word" lang={tl()}>{w.headword}</span>
          <span class="muted">{w.reading_display}</span>
          <span class="ch-word-en">{w.meanings.join("; ")}</span>
          {w.status === "learning" && <span class="chip status-learning">learning</span>}
        </li>
      ))}
    </ul>
  );
}

export function CharacterView({ char }: { char: string }) {
  const [d, setD] = useState<CharacterPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setD(null);
    setError(null);
    api.character(char).then(setD).catch((e) => setError(e.message));
    scrollTo(0, 0);
  }, [char]);

  const head = (
    <header class="reader-head">
      <Back fallback="#/chars" />
      <h1 class="sr-only">{char}</h1>
    </header>
  );
  if (error) return <main class="page">{head}<p class="error">{error}</p></main>;
  if (!d) return <main class="page">{head}<p class="muted">Loading…</p></main>;
  const ety = d.etymology;
  const etyLabel = ety?.type === "pictophonetic" ? "meaning + sound" : ety?.type === "ideographic" ? "meaning compound"
    : ety?.type === "pictographic" ? "picture" : null;

  return (
    <main class="page ch-page">
      {head}
      <section class="ch-hero">
        {d.has_strokes ? <StrokeOrder char={d.character} /> : <span class="ch-hero-glyph" lang={tl()}>{d.character}</span>}
        <div class="ch-hero-body">
          <div class="ch-hero-reading">
            <Marked syllables={d.pinyin} />
            {canSpeak() && (
              <button class="icon-btn tiny" onClick={() => speak(d.character)} aria-label="Play"><PlayIcon /></button>
            )}
          </div>
          {d.definition && <p class="ch-def">{d.definition}</p>}
          <div class="lk-meta">
            <span class={`chip ${d.status === "new" ? "chip-quiet" : `status-${d.status}`}`}>{statusLabel[d.status]}</span>
            {d.frequency && (
              <span class="chip chip-quiet" title={`${d.frequency.per_million.toFixed(1)} per million words (SUBTLEX-CH)`}>
                #{num(d.frequency.rank)} most common
              </span>
            )}
            {etyLabel && <span class="chip chip-quiet">{etyLabel}</span>}
            {d.transparency === "opaque" && <span class="chip chip-warn">parts mislead</span>}
          </div>
        </div>
      </section>

      {d.parts.length > 0 && (
        <section class="card">
          <h2>Parts <span class="muted ch-ids" lang={tl()}>{d.decomposition}</span></h2>
          <ul class="ch-parts">
            {d.parts.map((p, i) => (
              <li key={i}>
                <a class="ch-part" href={compHref(p.component)}>
                  <span class="ch-part-glyph" lang={tl()}>{p.component}</span>
                  <span class="ch-part-body">
                    <span>
                      {p.gloss ?? <span class="muted">no meaning recorded</span>}
                      {p.pinyin.length > 0 && <span class="muted"> · {p.pinyin[0]}</span>}
                    </span>
                    <span class="muted small">
                      {p.members.length > 1 && <span lang={tl()}>{p.members.join(" ")} · </span>}
                      {p.yours > 0 ? `in ${p.yours} of your characters` : "see characters with it"}
                      {p.decomposition && <span lang={tl()}> · {p.decomposition}</span>}
                    </span>
                  </span>
                  {p.role && <span class={`chip ${p.role === "sound" ? "chip-quiet" : ""}`}>{p.role}</span>}
                </a>
              </li>
            ))}
          </ul>
          {d.radical && (
            <p class="muted small">
              Radical <a href={compHref(d.radical)} lang={tl()} class="ch-inline">{d.radical}</a>
              {d.radical_family && d.radical_family !== d.radical && <span lang={tl()}> ({d.radical_family})</span>}
            </p>
          )}
        </section>
      )}

      <Notes notes={d.notes} transparency={d.transparency} />

      <section class="card">
        <h2>Your words with {d.character}</h2>
        {d.words.length ? <WordList words={d.words} /> : (
          <p class="muted small">None yet. Words you add to reviews or mark known show up here.</p>
        )}
        {d.more_words.length > 0 && (
          <>
            <h3 class="sub-h">HSK words to meet</h3>
            <WordList words={d.more_words} />
          </>
        )}
      </section>

      <div class="row wrap">
        {d.has_strokes && !d.writing && (
          <button class="btn" onClick={() => api.handwritingAdd({ characters: [d.character] })
            .then((r) => {
              toast(r.created.length ? `${d.character} added to Writing` : `Already practising ${d.character}`);
              setD({ ...d, writing: true });
            })
            .catch((e) => toast((e as Error).message))}>
            Practise writing
          </button>
        )}
        {d.writing && <span class="muted small">In your Writing reviews</span>}
        <a class="btn quiet" href="#/chars">All characters</a>
      </div>
      <p class="attribution">{d.attribution}</p>
    </main>
  );
}

function ComponentView({ component }: { component: string }) {
  const [d, setD] = useState<ComponentResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const [direct, setDirect] = useState(false);
  useEffect(() => {
    setError(null);
    api.component(component, { all, direct }).then(setD).catch((e) => setError(e.message));
  }, [component, all, direct]);

  const mine = d?.characters.filter((c) => c.status !== "new") ?? [];
  const others = d?.characters.filter((c) => c.status === "new") ?? [];
  return (
    <main class="page">
      <header class="reader-head">
        <Back fallback="#/chars" />
        <div>
          <h1 class="ch-comp-title" lang={tl()}>{d ? d.family.members.join(" ") : component}</h1>
          {d && (
            <p class="muted">
              {d.family.definition ?? "component"}
              {d.family.pinyin[0] ? ` · ${d.family.pinyin[0]}` : ""}
            </p>
          )}
        </div>
      </header>
      {error && <p class="error">{error}</p>}
      {!d && !error && <p class="muted">Loading…</p>}
      {d && (
        <>
          <p class="muted small">
            {num(d.counts.total)} characters contain {d.family.members.length > 1 ? "this family" : component}
            {d.counts.known + d.counts.learning > 0 && <> · <b>{d.counts.known}</b> you know, <b>{d.counts.learning}</b> learning</>}.
            {" "}Parts of parts count too (shown as “in 青”).
          </p>
          <div class="row wrap ch-filters">
            <label class="toggle">
              <input type="checkbox" checked={direct} onChange={(e) => setDirect(e.currentTarget.checked)} />
              <span>Direct parts only</span>
            </label>
            {(d.filtered || all) && (
              <label class="toggle">
                <input type="checkbox" checked={all} onChange={(e) => setAll(e.currentTarget.checked)} />
                <span>Include rare and traditional</span>
              </label>
            )}
          </div>
          {mine.length > 0 && (
            <section class="card">
              <h2>Yours</h2>
              <div class="ch-grid">{mine.map((c) => <Tile key={c.character} c={c} via={c.via} />)}</div>
            </section>
          )}
          {others.length > 0 && (
            <section class="card">
              <h2>{mine.length ? "More, most common first" : "Most common first"}</h2>
              <div class="ch-grid">{others.map((c) => <Tile key={c.character} c={c} via={c.via} />)}</div>
              {d.counts.total > d.characters.length && (
                <p class="muted small">Showing {d.characters.length} of {num(d.counts.total)}.</p>
              )}
            </section>
          )}
          {d.characters.length === 0 && <p class="muted">No characters found.</p>}
          <p class="attribution">{d.attribution}</p>
        </>
      )}
    </main>
  );
}

function Overview() {
  const [d, setD] = useState<CharactersOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => void api.characters().then(setD).catch((e) => setError(e.message)), []);

  function submit(e: Event, to: "char" | "chars") {
    e.preventDefault();
    const ch = [...q.trim()][0];
    if (ch) go(to === "char" ? `/char/${ch}` : `/chars/${ch}`);
  }

  return (
    <main class="page">
      <header class="reader-head">
        <Back fallback="#/progress" />
        <h1>Characters</h1>
      </header>
      <form class="row-input ch-search" onSubmit={(e) => submit(e, "char")}>
        <input type="text" lang={tl()} value={q} onInput={(e) => setQ(e.currentTarget.value)}
          placeholder="A character or component, e.g. 氵" aria-label="Character or component" maxLength={4} />
        <button class="btn" type="submit" disabled={!q.trim()}>Open</button>
        <button class="btn quiet" type="button" disabled={!q.trim()} onClick={(e) => submit(e, "chars")}>Characters with it</button>
      </form>
      {error && <p class="error">{error}</p>}
      {!d && !error && <p class="muted">Loading…</p>}
      {d && (
        <>
          <p class="muted small">
            <b>{num(d.counts.known)}</b> characters known and <b>{num(d.counts.learning)}</b> learning, from the words
            you know or review. A dot marks characters whose parts mislead.
          </p>
          {d.groups.length > 0 && (
            <section class="card">
              <h2>By component</h2>
              <p class="muted small">The parts that appear in most of your characters. Tap one to see every character with it.</p>
              <ul class="ch-groups">
                {d.groups.map((g) => (
                  <li key={g.key}>
                    <a class="ch-group-head" href={compHref(g.members[0])}>
                      <span class="ch-part-glyph" lang={tl()}>{g.members[0]}</span>
                      <span class="ch-part-body">
                        <span>{g.definition ? g.definition.split(/[;,]/)[0] : "component"}</span>
                        <span class="muted small">{g.count} of yours ›</span>
                      </span>
                    </a>
                    <span class="ch-group-chars" lang={tl()}>
                      {g.characters.slice(0, 16).map((ch) => <a key={ch} href={charHref(ch)}>{ch}</a>)}
                      {g.characters.length > 16 && <span class="muted"> …</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {d.characters.length > 0 ? (
            <section class="card">
              <h2>All your characters</h2>
              <div class="ch-grid">{d.characters.map((c) => <Tile key={c.character} c={c} />)}</div>
            </section>
          ) : (
            <section class="card empty">
              <p class="empty-glyph" lang={tl()}>字</p>
              <p class="muted">Characters appear here once you add words to reviews or mark them known.
                Try <a href={compHref("氵")}>氵 (water)</a> or <a href={compHref("口")}>口 (mouth)</a> to explore.</p>
            </section>
          )}
          <p class="attribution">{d.attribution}</p>
        </>
      )}
    </main>
  );
}

/** #/chars (overview) and #/chars/氵 (component explorer). */
export function Characters({ component }: { component?: string }) {
  return component ? <ComponentView key={component} component={component} /> : <Overview />;
}
