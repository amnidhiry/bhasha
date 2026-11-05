import { useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError, type TutorScenario, type TutorSession, type TutorTurn, type Tok } from "../api";
import { LookupSheet, PlayIcon, type LookupTarget } from "../components/LookupSheet";
import { toast } from "../components/Toast";
import { diff } from "../diff";
import { go } from "../router";
import { speak } from "../speech";
import { WriteModes } from "./Journal";

const AUTOPLAY_KEY = "bhasha.tutor.autoplay";

function TokenText({ tokens, onTap }: { tokens: Tok[]; onTap: (t: Tok) => void }) {
  return (
    <span lang="zh-CN">
      {tokens.map((t, i) =>
        t.kind === "word" || t.kind === "proper" ? (
          <button key={i} class={`tok s-${t.kind === "proper" ? "proper" : t.status ?? "new"}`} onClick={() => onTap(t)}>
            {t.show_reading && t.syllables.length
              ? t.syllables.map((s, j) => <ruby key={j}>{s.text}<rt>{s.surface_display}</rt></ruby>)
              : t.surface}
          </button>
        ) : <span key={i}>{t.surface}</span>,
      )}
    </span>
  );
}

function Bubble({ t, last, onTap }: { t: TutorTurn; last: boolean; onTap: (tok: Tok, sentence: string) => void }) {
  const [en, setEn] = useState(false);
  const [hint, setHint] = useState(false);
  if (t.role === "learner") {
    const changed = t.corrected && t.corrected !== t.text;
    return (
      <li class="bubble mine">
        {changed ? (
          <p class="jr-diff" lang="zh-CN">{diff(t.text, t.corrected!).map((s, i) => <span key={i} class={`d-${s.kind}`}>{s.text}</span>)}</p>
        ) : <p lang="zh-CN">{t.text} <span class="ok small">✓</span></p>}
        {t.errors?.map((e, i) => (
          <p key={i} class="small bubble-note">
            <span class="chip chip-quiet">{e.label}</span> {e.explanation}{e.card_id ? " · card added" : ""}
          </p>
        ))}
      </li>
    );
  }
  return (
    <li class="bubble theirs">
      <p class="bubble-zh">{t.tokens ? <TokenText tokens={t.tokens} onTap={(tok) => onTap(tok, t.text)} /> : t.text}</p>
      <div class="bubble-tools">
        <button class="icon-btn tiny" aria-label="Play" onClick={() => speak(t.text)}><PlayIcon /></button>
        <button class={`link-btn inline ${en ? "on" : ""}`} onClick={() => setEn(!en)}>EN</button>
        {last && t.hint && <button class="link-btn inline" onClick={() => setHint(!hint)}>Hint</button>}
      </div>
      {en && t.english && <p class="small muted">{t.english}</p>}
      {hint && <p class="small bubble-hint">{t.hint}</p>}
    </li>
  );
}

function Chat({ id }: { id: number }) {
  const [s, setS] = useState<TutorSession | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState<LookupTarget | null>(null);
  const [autoplay, setAutoplay] = useState(() => {
    try { return localStorage.getItem(AUTOPLAY_KEY) !== "off"; } catch { return true; }
  });
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => void api.tutorSession(id).then(setS).catch((e) => toast(e.message)), [id]);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [s?.turns.length, busy]);

  async function send(ev: Event) {
    ev.preventDefault();
    const msg = text.trim();
    if (!msg || !s) return;
    setBusy(true);
    setS({ ...s, turns: [...s.turns, { id: -1, role: "learner", text: msg, english: null }] });
    setText("");
    try {
      const next = await api.tutorSay(s.id, msg);
      setS(next);
      const reply = next.turns[next.turns.length - 1];
      if (autoplay && reply?.role === "tutor") speak(reply.text);
      if (next.goal_met && !s.goal_met) toast("Goal reached! Keep chatting or end the conversation.");
    } catch (e) {
      setText(msg);
      setS(s);
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!s) return <main class="page"><p class="muted">Loading…</p></main>;
  const lastTutor = [...s.turns].reverse().find((t) => t.role === "tutor");
  return (
    <main class="page talk">
      <header class="talk-head">
        <a href="#/talk" class="back" aria-label="Back to scenarios">‹</a>
        <div>
          <h1>{s.scenario.title} <span class="muted" lang="zh-CN">{s.scenario.title_zh}</span></h1>
          <p class="small muted"><b>Goal:</b> {s.scenario.goal}</p>
        </div>
      </header>
      {s.goal_met && <p class="goal-banner small">Goal reached.</p>}
      <ul class="chat">
        {s.turns.map((t) => (
          <Bubble key={t.id} t={t} last={t === lastTutor}
            onTap={(tok, sentence) => setTarget({ surface: tok.surface, unitId: tok.unit_id, status: tok.status,
              syllables: tok.syllables, sentence, log: false })} />
        ))}
        {busy && <li class="bubble theirs typing" aria-label="Tutor is replying"><span /><span /><span /></li>}
      </ul>
      <div ref={end} />
      {s.status === "active" ? (
        <form class="chat-input" onSubmit={send}>
          <input lang="zh-CN" value={text} onInput={(e) => setText(e.currentTarget.value)} placeholder="用中文回答…"
            disabled={busy} autocomplete="off" />
          <button class="btn primary" disabled={busy || !text.trim()}>Send</button>
          <button type="button" class="btn quiet" disabled={busy}
            onClick={() => api.tutorEnd(s.id).then(setS).catch((e) => toast(e.message))}>End</button>
        </form>
      ) : (
        <section class="card talk-summary">
          <h2>{s.goal_met ? "Goal reached" : "Conversation ended"}</h2>
          <p class="muted small">
            {s.mistakes ? `${s.mistakes} correction${s.mistakes === 1 ? "" : "s"}; the ones with a gap to fill are now review cards.` : "No mistakes this time."}
          </p>
          <div class="row"><a class="btn primary" href="#/talk">Another scenario</a><a class="btn" href="#/review">Review</a></div>
        </section>
      )}
      <label class="toggle small autoplay">
        <input type="checkbox" checked={autoplay} onChange={(e) => {
          setAutoplay(e.currentTarget.checked);
          try { localStorage.setItem(AUTOPLAY_KEY, e.currentTarget.checked ? "on" : "off"); } catch { /* ignore */ }
        }} />
        <span>Read replies aloud</span>
      </label>
      <LookupSheet target={target} onClose={() => setTarget(null)} onChanged={() => {}} />
    </main>
  );
}

function Scenarios() {
  const [list, setList] = useState<TutorScenario[] | null>(null);
  const [recent, setRecent] = useState<Awaited<ReturnType<typeof api.tutorSessions>>>([]);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    api.tutorScenarios().then(setList).catch((e) => toast(e.message));
    api.tutorSessions().then(setRecent).catch(() => {});
  }, []);

  async function start(id: string) {
    setBusy(id);
    try {
      const s = await api.tutorStart(id);
      const first = s.turns[0];
      try { if (localStorage.getItem(AUTOPLAY_KEY) !== "off" && first) speak(first.text); } catch { /* ignore */ }
      go(`#/talk/${s.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        toast("Connect a model first: Progress → Text generation");
        go("#/progress");
      } else toast((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const active = recent.filter((r) => r.status === "active");
  return (
    <main class="page">
      <header class="page-head"><h1>Write</h1><WriteModes active="talk" /></header>
      <p class="muted">Role-play in Chinese with a tutor who sticks to words you know. Your mistakes are corrected as you go and become review cards.</p>
      {active.length > 0 && (
        <section class="card">
          <h2>Continue</h2>
          <ul class="text-list">
            {active.slice(0, 3).map((r) => (
              <li key={r.id}><a class="drill-row" href={`#/talk/${r.id}`}><span class="drill-title">{r.scenario.title}</span><span /><span class="muted small">›</span></a></li>
            ))}
          </ul>
        </section>
      )}
      <ul class="scenario-list">
        {list?.map((sc) => (
          <li key={sc.id} class="card scenario">
            <div>
              <h2>{sc.title} <span class="muted" lang="zh-CN">{sc.title_zh}</span>{(sc.completed ?? 0) > 0 && <span class="chip status-known">done ×{sc.completed}</span>}</h2>
              <p class="small muted">{sc.setting} You talk with {sc.role}.</p>
              <p class="small"><b>Goal:</b> {sc.goal}</p>
            </div>
            <button class="btn primary" disabled={!!busy} onClick={() => start(sc.id)}>{busy === sc.id ? "Starting…" : "Start"}</button>
          </li>
        ))}
      </ul>
    </main>
  );
}

export function Talk({ id }: { id?: number }) {
  return id ? <Chat id={id} /> : <Scenarios />;
}
