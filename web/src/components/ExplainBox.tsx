import { tl } from "../lang";
import { useState } from "preact/hooks";
import { api, ApiError } from "../api";

interface Explained {
  answer: string;
  chunks: { text: string; role: string }[];
  points: { name: string; url: string | null }[];
}

/** "Why 了 here?": ask about a sentence, answered at your level. */
export function ExplainBox({ sentence, focus }: { sentence: string; focus: string }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<Explained | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function ask(question: string) {
    setBusy(true);
    setErr(null);
    try {
      setRes(await api.explain(sentence, question, focus));
    } catch (e) {
      setErr(e instanceof ApiError && e.status === 409 ? "Connect a model first: Progress → Text generation." : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return <button class="link-btn" onClick={() => setOpen(true)}>Explain this sentence…</button>;
  }
  return (
    <div class="explain">
      <p class="explain-sentence" lang={tl()}>{sentence}</p>
      <div class="chips">
        <button class="chip-btn" disabled={busy} onClick={() => ask("Explain this sentence.")}>Explain the sentence</button>
        <button class="chip-btn" disabled={busy} onClick={() => ask(`Why is ${focus} used here?`)} lang={tl()}>Why {focus} here?</button>
      </div>
      <form class="row-input" onSubmit={(e) => { e.preventDefault(); if (q.trim()) void ask(q.trim()); }}>
        <input value={q} onInput={(e) => setQ(e.currentTarget.value)} placeholder="Or ask anything, e.g. 才 vs 就?" disabled={busy} />
        <button class="btn" disabled={busy || !q.trim()}>Ask</button>
      </form>
      {busy && <p class="muted small">Thinking…</p>}
      {err && <p class="error small">{err}</p>}
      {res && (
        <div class="explain-answer">
          {res.chunks.length > 0 && (
            <ol class="chunks">
              {res.chunks.map((c, i) => <li key={i}><span lang={tl()}>{c.text}</span><small>{c.role}</small></li>)}
            </ol>
          )}
          <p>{res.answer}</p>
          {res.points.length > 0 && (
            <p class="small">
              Grammar Wiki:{" "}
              {res.points.map((p, i) => p.url ? <a key={i} href={p.url} target="_blank" rel="noopener" class="wiki-link">{p.name}</a> : <span key={i} class="wiki-link">{p.name}</span>)}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
