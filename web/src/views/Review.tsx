import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { api, type DueCard } from "../api";
import { PlayIcon } from "../components/LookupSheet";
import { Pinyin } from "../components/Pinyin";
import { cachedParams, cachedQueue, cachedWaiting, enqueue, flush, pending, saveParams, saveQueue, saveWaiting } from "../outbox";
import { makeScheduler, review as localReview } from "../scheduler";
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
};

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
  const [queue, setQueue] = useState<DueCard[] | null>(null);
  const [waiting, setWaiting] = useState<DueCard[]>(cachedWaiting);
  const [sched, setSched] = useState<Awaited<ReturnType<typeof makeScheduler>> | null>(null);
  const [offline, setOffline] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [doneCount, setDoneCount] = useState(0);
  const [unsynced, setUnsynced] = useState(pending().length);
  const shownAt = useRef(Date.now());

  const load = useCallback(async () => {
    setUnsynced(await flush());
    const params = await api.schedulerParams().then((p) => (saveParams(p), p)).catch(() => cachedParams());
    if (params) makeScheduler(params).then(setSched).catch(() => setSched(null));
    const waitingIds = () => new Set(pending().map((p) => p.card_id));
    let q: DueCard[];
    try {
      const fresh = await api.due();
      // Ratings still in the outbox haven't reached the server; don't show those cards twice.
      const skip = waitingIds();
      q = fresh.filter((c) => !skip.has(c.card_id));
      setOffline(false);
    } catch {
      const skip = waitingIds();
      q = cachedQueue().filter((c) => !skip.has(c.card_id));
      setOffline(true);
    }
    // Keep locally scheduled learning cards the server list doesn't already include.
    const inQueue = new Set(q.map((c) => c.card_id));
    const w = cachedWaiting().filter((c) => !inQueue.has(c.card_id));
    saveQueue(q);
    saveWaiting(w);
    setQueue(q);
    setWaiting(w);
  }, []);
  useEffect(() => void load(), [load]);
  useEffect(() => onCount((queue?.length ?? 0) + waiting.filter((c) => dueMs(c) <= Date.now()).length), [queue, waiting, onCount]);

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
    saveQueue(q);
    saveWaiting(rest);
  }, [now, waiting, queue]);

  const pullNext = () => {
    if (!waiting.length || !queue) return;
    const [next, ...rest] = [...waiting].sort((a, b) => dueMs(a) - dueMs(b));
    setQueue([next, ...queue]);
    setWaiting(rest);
    saveWaiting(rest);
  };

  const card = queue?.[0];
  useEffect(() => {
    setRevealed(false);
    shownAt.current = Date.now();
    if (card?.facet === "listening") speak(card.headword);
  }, [card?.card_id]);

  const reveal = () => {
    if (!card || revealed) return;
    setRevealed(true);
    if (card.facet === "reading") speak(card.headword);
  };

  const rate = (rating: 1 | 2 | 3 | 4) => {
    if (!card || !revealed) return;
    const at = new Date();
    enqueue({ card_id: card.card_id, rating, reviewed_at: at.toISOString(), duration_ms: Date.now() - shownAt.current });
    const rest = queue!.slice(1);
    saveQueue(rest);
    setQueue(rest);
    if (sched) {
      const next = localReview(sched, card.fsrs, card.card_id, rating, at);
      if (new Date(next.due).getTime() - at.getTime() <= LOOKAHEAD_MS) {
        const w = [...waiting.filter((c) => c.card_id !== card.card_id), { ...card, fsrs: next, is_new: false }];
        setWaiting(w);
        saveWaiting(w);
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

  if (!queue) return <main class="page"><p class="muted">Loading reviews…</p></main>;

  if (!card && waiting.length) {
    const next = Math.min(...waiting.map(dueMs));
    const secs = Math.max(0, Math.ceil((next - now) / 1000));
    return (
      <main class="page">
        <header class="page-head"><h1>Review</h1></header>
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
        <header class="page-head"><h1>Review</h1></header>
        <section class="empty card">
          <p class="empty-glyph" lang="zh-CN" aria-hidden="true">{doneCount ? "好" : "空"}</p>
          <h2>{doneCount ? `${doneCount} reviewed. Nothing else is due.` : "Nothing due"}</h2>
          <p class="muted">
            {doneCount
              ? "Everything due today is done. Reading next is a good use of the time."
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
  return (
    <main class="page review">
      <header class="rv-top">
        <span class="muted">{queue.length} left{doneCount ? ` · ${doneCount} done` : ""}</span>
        <span class="rv-tags">
          <span class="chip chip-quiet">{card.facet}</span>
          {card.is_new && <span class="chip">new</span>}
          {card.leech && <span class="chip chip-warn" title="Failed many times. Look at its parts or the sentence.">keeps slipping</span>}
          {offline && <span class="chip chip-warn">offline</span>}
        </span>
      </header>

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
          </div>
        ) : (
          <button class="btn wide reveal" onClick={(e) => { e.stopPropagation(); reveal(); }}>Show answer</button>
        )}
      </section>

      <div class={`ratings ${revealed ? "" : "is-hidden"}`} aria-hidden={!revealed}>
        {RATINGS.map(({ r, label, hint }) => (
          <button key={r} class={`rate rate-${r}`} disabled={!revealed} onClick={() => rate(r)}>
            <span>{label}</span>
            <small>{hint}</small>
          </button>
        ))}
      </div>
      <p class="muted small kbd-hint">Space to reveal · 1–4 to rate</p>
    </main>
  );
}
