import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { api, type DueCard, type Example } from "../api";
import { PlayIcon } from "../components/LookupSheet";
import { Pinyin } from "../components/Pinyin";
import { cachedParams, cachedQueue, cachedWaiting, enqueue, flush, pending, saveParams, saveQueue, saveWaiting, type Mode } from "../outbox";
import { WritingPad, type PadHandle } from "../components/WritingPad";
import { CardHelp } from "../components/CardHelp";
import { makeSchedulerSet, review as localReview } from "../scheduler";
import { canSpeak, speak } from "../speech";

const RATINGS = [
  { r: 1, label: "Again", hint: "Forgot" },
  { r: 2, label: "Hard", hint: "Barely" },
  { r: 3, label: "Good", hint: "Got it" },
  { r: 4, label: "Easy", hint: "Instant" },
] as const;

/** Cards whose next step is within this window come back in this session. */
const LOOKAHEAD_MS = 60 * 60 * 1000;
const dueMs = (c: DueCard) => new Date(c.fsrs.due).getTime();

function useClock(active: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

const FACET_PROMPT: Record<string, string> = {
  meaning: "What does it mean?",
  reading: "How is it pronounced? Say it aloud, tones included.",
  listening: "Listen. What did you hear?",
  handwriting: "Write it from memory, stroke by stroke.",
  cloze: "Fill the gap. You got this one wrong in your journal.",
};

/** The corrected sentence with the answer blanked (or filled in, once revealed). */
function Cloze({ sentence, answer, revealed }: { sentence: string; answer: string; revealed: boolean }) {
  const i = sentence.indexOf(answer);
  if (i < 0) return <p class="rv-cloze" lang="zh-CN">{sentence}</p>;
  return (
    <p class="rv-cloze" lang="zh-CN">
      {sentence.slice(0, i)}
      <span class={revealed ? "filled" : "blank"}>{revealed ? answer : "\u00a0".repeat(Math.max(2, answer.length * 2))}</span>
      {sentence.slice(i + answer.length)}
    </p>
  );
}

/** Hanzi Writer's mistake count -> suggested FSRS rating. Hints or giving up mean Again. */
export function suggestRating(mistakes: number, helped: boolean): 1 | 2 | 3 {
  if (helped || mistakes >= 3) return 1;
  return mistakes >= 1 ? 2 : 3;
}

const MODE_KEY = "bhasha.reviewMode";
const initialMode = (): Mode => {
  try {
    return localStorage.getItem(MODE_KEY) === "writing" ? "writing" : "words";
  } catch {
    return "words";
  }
};

/** The word with this character blanked out, as a cue: 银行 -> ＿行. */
const masked = (context: string | null, ch: string) => (context && context.includes(ch) && context !== ch ? context.split(ch).join("＿") : null);

function Sentence({ text, word }: { text: string; word: string }) {
  const i = text.indexOf(word);
  if (i < 0) return <p class="rv-sentence" lang="zh-CN">{text}</p>;
  return (
    <p class="rv-sentence" lang="zh-CN">
      {text.slice(0, i)}<mark>{word}</mark>{text.slice(i + word.length)}
    </p>
  );
}

export function Review({ onCount }: { onCount: (n: number) => void }) {
  const [mode, setModeState] = useState<Mode>(initialMode);
  const [queue, setQueue] = useState<DueCard[] | null>(null);
  const [waiting, setWaiting] = useState<DueCard[]>(() => cachedWaiting(mode));
  const [suggested, setSuggested] = useState<1 | 2 | 3 | null>(null);
  const [mistakes, setMistakes] = useState<number | null>(null);
  const helped = useRef(false);
  const [example, setExample] = useState<Example | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const pad = useRef<PadHandle>(null);
  const setMode = (m: Mode) => {
    try { localStorage.setItem(MODE_KEY, m); } catch { /* ignore */ }
    setQueue(null);
    setWaiting(cachedWaiting(m));
    setModeState(m);
  };
  const [sched, setSched] = useState<Awaited<ReturnType<typeof makeSchedulerSet>> | null>(null);
  const [paused, setPaused] = useState<{ backlog: number; threshold: number } | null>(null);
  const [offline, setOffline] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [doneCount, setDoneCount] = useState(0);
  const [unsynced, setUnsynced] = useState(pending().length);
  const shownAt = useRef(Date.now());

  const load = useCallback(async () => {
    setUnsynced(await flush());
    const params = await api.schedulerParams().then((p) => (saveParams(p), p)).catch(() => cachedParams());
    if (params) makeSchedulerSet(params).then((f) => setSched(() => f)).catch(() => setSched(null));
    api.reviewStatus(mode).then((st) => setPaused(st.new_paused ? st : null)).catch(() => setPaused(null));
    const waitingIds = () => new Set(pending().map((p) => p.card_id));
    let q: DueCard[];
    try {
      const fresh = await api.due(100, mode);
      // Ratings still in the outbox haven't reached the server; don't show those cards twice.
      const skip = waitingIds();
      q = fresh.filter((c) => !skip.has(c.card_id));
      setOffline(false);
    } catch {
      const skip = waitingIds();
      q = cachedQueue(mode).filter((c) => !skip.has(c.card_id));
      setOffline(true);
    }
    // Keep locally scheduled learning cards the server list doesn't already include.
    const inQueue = new Set(q.map((c) => c.card_id));
    const w = cachedWaiting(mode).filter((c) => !inQueue.has(c.card_id));
    saveQueue(q, mode);
    saveWaiting(w, mode);
    setQueue(q);
    setWaiting(w);
  }, [mode]);
  useEffect(() => void load(), [load]);
  useEffect(() => { if (mode === "words") onCount((queue?.length ?? 0) + waiting.filter((c) => dueMs(c) <= Date.now()).length); }, [queue, waiting, onCount, mode]);

  // Move learning cards back into the queue when their step is up.
  const now = useClock(waiting.length > 0);
  useEffect(() => {
    if (!queue) return;
    const ready = waiting.filter((c) => dueMs(c) <= now);
    if (!ready.length) return;
    const rest = waiting.filter((c) => dueMs(c) > now);
    const q = [...ready, ...queue];
    setQueue(q);
    setWaiting(rest);
    saveQueue(q, mode);
    saveWaiting(rest, mode);
  }, [now, waiting, queue]);

  const pullNext = () => {
    if (!waiting.length || !queue) return;
    const [next, ...rest] = [...waiting].sort((a, b) => dueMs(a) - dueMs(b));
    setQueue([next, ...queue]);
    setWaiting(rest);
    saveWaiting(rest, mode);
  };

  const card = queue?.[0];
  useEffect(() => {
    setRevealed(false);
    setSuggested(null);
    setMistakes(null);
    setExample(null);
    setShowHelp(false);
    helped.current = false;
    shownAt.current = Date.now();
    if (card?.facet === "listening") speak(card.headword);
  }, [card?.card_id]);

  const reveal = () => {
    if (!card || revealed) return;
    if (card.facet === "handwriting") {
      // "Show answer" on a writing card means giving up: animate the strokes.
      helped.current = true;
      pad.current?.giveUp();
      setSuggested(1);
    }
    setRevealed(true);
    if (card.facet === "reading") speak(card.headword);
    if (card.facet !== "handwriting" && !card.cloze) {
      // A second, human-written example (not the one the word was mined from).
      const id = card.card_id;
      api.examples(card.unit_id, 3)
        .then((ex) => {
          const other = ex.find((e) => e.text !== card.context_sentence);
          if (other && queue?.[0]?.card_id === id) setExample(other);
        })
        .catch(() => {});
    }
  };

  const rate = (rating: 1 | 2 | 3 | 4) => {
    if (!card || !revealed) return;
    const at = new Date();
    enqueue({ card_id: card.card_id, rating, reviewed_at: at.toISOString(), duration_ms: Date.now() - shownAt.current,
      source: card.facet === "handwriting" ? "handwriting" : "queue" });
    const rest = queue!.slice(1);
    saveQueue(rest, mode);
    setQueue(rest);
    if (sched) {
      const next = localReview(sched(card.facet), card.fsrs, card.card_id, rating, at);
      if (new Date(next.due).getTime() - at.getTime() <= LOOKAHEAD_MS) {
        const w = [...waiting.filter((c) => c.card_id !== card.card_id), { ...card, fsrs: next, is_new: false }];
        setWaiting(w);
        saveWaiting(w, mode);
      }
    }
    setDoneCount((n) => n + 1);
    setTimeout(() => setUnsynced(pending().length), 400);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === " " || e.key === "Enter") { e.preventDefault(); reveal(); }
      if (["1", "2", "3", "4"].includes(e.key)) rate(Number(e.key) as 1 | 2 | 3 | 4);
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  });

  const modeSwitch = (
    <div class="seg mode-switch" role="tablist" aria-label="Session">
      <button role="tab" aria-selected={mode === "words"} class={mode === "words" ? "on" : ""} onClick={() => mode !== "words" && setMode("words")}>Words</button>
      <button role="tab" aria-selected={mode === "writing"} class={mode === "writing" ? "on" : ""} onClick={() => mode !== "writing" && setMode("writing")}>Writing</button>
    </div>
  );

  if (!queue) return <main class="page"><header class="page-head"><h1>Review</h1>{modeSwitch}</header><p class="muted">Loading…</p></main>;

  if (!card && waiting.length) {
    const next = Math.min(...waiting.map(dueMs));
    const secs = Math.max(0, Math.ceil((next - now) / 1000));
    return (
      <main class="page">
        <header class="page-head"><h1>Review</h1>{modeSwitch}</header>
        <section class="empty card">
          <p class="countdown" aria-live="off">{Math.floor(secs / 60)}:{String(secs % 60).padStart(2, "0")}</p>
          <h2>{waiting.length === 1 ? "1 card is" : `${waiting.length} cards are`} between learning steps</h2>
          <p class="muted">
            The next one comes back on its own. Spacing even a few minutes helps it stick, so read something meanwhile.
          </p>
          <div class="row">
            <a class="btn primary" href="#/">Go read</a>
            <button class="btn" onClick={pullNext}>Show it now</button>
          </div>
          {unsynced > 0 && <p class="muted small">{unsynced} reviews waiting to sync</p>}
        </section>
      </main>
    );
  }

  if (!card) {
    return (
      <main class="page">
        <header class="page-head"><h1>Review</h1>{modeSwitch}</header>
        <section class="empty card">
          <p class="empty-glyph" lang="zh-CN" aria-hidden="true">{doneCount ? "好" : "空"}</p>
          <h2>{doneCount ? `${doneCount} reviewed. Nothing else is due.` : "Nothing due"}</h2>
          <p class="muted">
            {doneCount
              ? "Everything due today is done. Reading next is a good use of the time."
              : mode === "writing"
                ? "Start characters from the official HSK list in Progress, or tap Write on a character when you look a word up."
                : "Add words from the reader. They show up here once you've met them in a text."}
          </p>
          <div class="row">
            <a class="btn primary" href="#/">Go read</a>
            <button class="btn" onClick={load}>Check again</button>
          </div>
          {unsynced > 0 && <p class="muted small">{unsynced} reviews waiting to sync</p>}
        </section>
      </main>
    );
  }

  const listening = card.facet === "listening";
  const writing = card.facet === "handwriting";
  const cloze = card.cloze ?? null;
  const cue = writing ? masked(card.context_sentence, card.headword) : null;
  return (
    <main class="page review">
      {paused && (
        <p class="paused-note small">
          New cards paused: {paused.backlog} reviews are waiting (more than {paused.threshold}). Clearing them first keeps
          reading time free. <a href="#/progress">Change</a>
        </p>
      )}
      <header class="rv-top">
        {modeSwitch}
        <span class="muted">{queue.length} left{doneCount ? ` · ${doneCount} done` : ""}</span>
        <span class="rv-tags">
          <span class="chip chip-quiet">{cloze ? "fill-in" : card.facet}</span>
          {card.is_new && <span class="chip">new</span>}
          {card.leech && <span class="chip chip-warn" title="Failed many times. Look at its parts or the sentence.">keeps slipping</span>}
          {offline && <span class="chip chip-warn">offline</span>}
        </span>
      </header>

      {writing ? (
      <section class="rv-card card writing" aria-live="polite">
        <p class="rv-prompt muted">{FACET_PROMPT.handwriting}</p>
        <div class="rv-cue">
          <Pinyin numeric={card.reading} display={card.reading_display} />
          <span class="rv-cue-meaning">{card.meanings.slice(0, 2).join("; ")}</span>
          {cue && <span class="rv-cue-word" lang="zh-CN">{cue}</span>}
        </div>
        <WritingPad ref={pad} char={card.headword} onDone={(m) => {
          setMistakes(m);
          setSuggested(suggestRating(m, helped.current));
          setRevealed(true);
          speak(card.headword);
        }} />
        {revealed ? (
          <p class="rv-result">
            {helped.current ? "Watch the stroke order, then rate it." : mistakes === 0 ? "Clean: no mistakes." : `${mistakes} mistake${mistakes === 1 ? "" : "s"}.`}
          </p>
        ) : (
          <div class="row tight center">
            <button class="btn quiet" onClick={() => { helped.current = true; pad.current?.hint(); }}>Hint</button>
            <button class="btn" onClick={reveal}>I don't remember</button>
          </div>
        )}
      </section>
      ) : cloze ? (
      <section class={`rv-card card ${revealed ? "is-revealed" : ""}`} onClick={reveal} aria-live="polite">
        <p class="rv-prompt muted">{FACET_PROMPT.cloze}</p>
        <Cloze sentence={cloze.sentence} answer={cloze.answer} revealed={revealed} />
        {cloze.english && <p class="muted">{cloze.english}</p>}
        {revealed ? (
          <div class="rv-answer">
            <p>
              {cloze.wrong ? <>You wrote <s lang="zh-CN">{cloze.wrong}</s>. </> : <>You left this out. </>}
              {cloze.explanation}
            </p>
            {canSpeak() && (
              <button class="icon-btn" onClick={(e) => { e.stopPropagation(); speak(cloze.sentence); }} aria-label="Play sentence">
                <PlayIcon />
              </button>
            )}
          </div>
        ) : (
          <button class="btn wide reveal" onClick={(e) => { e.stopPropagation(); reveal(); }}>Show answer</button>
        )}
      </section>
      ) : (
      <section class={`rv-card card ${revealed ? "is-revealed" : ""}`} onClick={reveal}
        aria-live="polite">
        <p class="rv-prompt muted">{FACET_PROMPT[card.facet] ?? "Recall it"}</p>

        {listening && !revealed ? (
          <button class="rv-listen" onClick={(e) => { e.stopPropagation(); speak(card.headword); }} aria-label="Play again">
            <PlayIcon />
          </button>
        ) : (
          <div class="rv-word" lang="zh-CN">{card.headword}</div>
        )}

        {!listening && card.context_sentence && (
          <Sentence text={card.context_sentence} word={card.headword} />
        )}

        {revealed ? (
          <div class="rv-answer">
            <div class="rv-reading">
              <Pinyin numeric={card.reading} display={card.reading_display} />
              {canSpeak() && (
                <button class="icon-btn" onClick={(e) => { e.stopPropagation(); speak(card.headword); }} aria-label="Play">
                  <PlayIcon />
                </button>
              )}
            </div>
            <ul class="rv-meanings">
              {card.meanings.slice(0, 4).map((m, i) => <li key={i}>{m}</li>)}
            </ul>
            {card.classifiers.length > 0 && <p class="muted" lang="zh-CN">MW {card.classifiers.join(" · ")}</p>}
            {listening && card.context_sentence && <Sentence text={card.context_sentence} word={card.headword} />}
            {card.leech && !showHelp && (
              <button class="btn wide" onClick={(e) => { e.stopPropagation(); setShowHelp(true); }}>
                Help with this word (failed {card.fsrs.lapses}×)
              </button>
            )}
            {showHelp && (
              <CardHelp cardId={card.card_id} onSuspended={() => {
                const rest = queue!.slice(1);
                saveQueue(rest, mode);
                setQueue(rest);
              }} />
            )}
            {example && (
              <div class="rv-example">
                <Sentence text={example.text} word={card.headword} />
                <p class="muted small">{example.translation} · <a href={example.url} target="_blank" rel="noopener" onClick={(e) => e.stopPropagation()}>Tatoeba</a></p>
              </div>
            )}
          </div>
        ) : (
          <button class="btn wide reveal" onClick={(e) => { e.stopPropagation(); reveal(); }}>Show answer</button>
        )}
      </section>
      )}

      <div class={`ratings ${revealed ? "" : "is-hidden"}`} aria-hidden={!revealed}>
        {RATINGS.map(({ r, label, hint }) => (
          <button key={r} class={`rate rate-${r} ${suggested === r ? "suggested" : ""}`} disabled={!revealed} onClick={() => rate(r)}>
            <span>{label}</span>
            <small>{hint}</small>
          </button>
        ))}
      </div>
      <p class="muted small kbd-hint">Space to reveal · 1–4 to rate</p>
    </main>
  );
}
