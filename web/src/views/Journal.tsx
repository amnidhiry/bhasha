import { lang, tl } from "../lang";
import { useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError, type JournalEntry } from "../api";
import { toast } from "../components/Toast";
import { diff } from "../diff";
import { go } from "../router";
import { canSpeak, speak } from "../speech";

function Diff({ a, b }: { a: string; b: string }) {
  return (
    <p class="jr-diff" lang={tl()}>
      {diff(a, b).map((s, i) => <span key={i} class={`d-${s.kind}`}>{s.text}</span>)}
    </p>
  );
}

function Entry({ e, onRetry }: { e: JournalEntry; onRetry: () => void }) {
  const date = new Date(e.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  if (e.status !== "done") {
    return (
      <li class="card jr-entry">
        <p class="muted small">{date}</p>
        <p class="jr-text" lang={tl()}>{e.text}</p>
        {e.status === "queued" ? (
          <p class="muted small"><span class="spinner inline" aria-hidden="true" /> Correcting…</p>
        ) : (
          <p class="error small">{e.error ?? "Correction failed."} <button class="link-btn inline" onClick={onRetry}>Retry</button></p>
        )}
      </li>
    );
  }
  return (
    <li class="card jr-entry">
      <p class="muted small">{date} · {e.errors.length ? `${e.errors.length} to fix` : "no mistakes"}</p>
      {e.sentences.map((s, i) => (
        <div key={i} class="jr-sentence">
          {s.original === s.corrected ? <p class="jr-ok" lang={tl()}>{s.corrected} <span class="ok small">✓</span></p> : <Diff a={s.original} b={s.corrected} />}
          <p class="muted small">
            {s.english}
            {canSpeak() && <button class="link-btn inline" onClick={() => speak(s.corrected)}>▶</button>}
          </p>
          {e.errors.filter((x) => x.sentence_index === i).map((x) => (
            <p key={x.id} class="jr-error small">
              <span class="chip chip-quiet">{x.label}</span>{" "}
              <span lang={tl()}>{x.wrong ? <s>{x.wrong}</s> : <i>(missing)</i>} → <b>{x.right || <i>(remove)</i>}</b></span>{" "}
              {x.explanation}
              {x.card_id && <span class="muted"> · card added</span>}
            </p>
          ))}
        </div>
      ))}
      {e.comment && <p class="jr-comment small">{e.comment}</p>}
    </li>
  );
}

export function WriteModes({ active }: { active: "journal" | "talk" }) {
  return (
    <nav class="seg mode-switch" aria-label="Write or talk">
      <a href="#/journal" class={active === "journal" ? "on" : ""} aria-current={active === "journal" ? "page" : undefined}>Journal</a>
      <a href="#/talk" class={active === "talk" ? "on" : ""} aria-current={active === "talk" ? "page" : undefined}>Talk</a>
    </nav>
  );
}

export function Journal() {
  const [prompt, setPrompt] = useState<{ words: string[]; idea: string } | null>(null);
  const [data, setData] = useState<Awaited<ReturnType<typeof api.journal>> | null>(null);
  const [text, setText] = useState(() => {
    try { return localStorage.getItem("bhasha.journal.draft") ?? ""; } catch { return ""; }
  });
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const load = () => api.journal().then((d) => {
    setData(d);
    clearTimeout(timer.current);
    if (d.entries.some((e) => e.status === "queued")) timer.current = window.setTimeout(load, 3000);
  }).catch((e) => toast(e.message));
  useEffect(() => {
    api.journalPrompt().then(setPrompt).catch(() => {});
    void load();
    return () => clearTimeout(timer.current);
  }, []);
  useEffect(() => {
    try { localStorage.setItem("bhasha.journal.draft", text); } catch { /* ignore */ }
  }, [text]);

  async function submit(ev: Event) {
    ev.preventDefault();
    if (text.trim().length < 2) return;
    setBusy(true);
    try {
      await api.journalWrite(text.trim(), prompt ?? {});
      setText("");
      toast("Sent for correction. Mistakes become review cards.");
      void load();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        toast("Connect a model first: Progress → Text generation");
        go("#/progress");
      } else toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const cats = data ? Object.entries(data.categories) : [];
  return (
    <main class="page">
      <header class="page-head"><h1>Write</h1><WriteModes active="journal" /></header>
      <form class="card form" onSubmit={submit}>
        {prompt && (
          <div class="jr-prompt">
            <p class="small"><b>Idea:</b> {prompt.idea}</p>
            {prompt.words.length > 0 && (
              <p class="small">
                <b>Try using:</b>{" "}
                {prompt.words.map((w) => (
                  <button type="button" key={w} lang={tl()} class={`chip-btn ${text.includes(w) ? "on" : ""}`}
                    onClick={() => setText((t) => t + w)}>{w}</button>
                ))}
              </p>
            )}
          </div>
        )}
        <label>
          <span>A few sentences in {lang().adjective}</span>
          <textarea lang={tl()} rows={5} value={text} onInput={(e) => setText(e.currentTarget.value)}
            placeholder="今天我……" />
        </label>
        <div class="form-foot">
          <span class="muted">Corrections keep your meaning and explain each change. Every mistake becomes a fill-in card.</span>
          <button class="btn primary" disabled={busy || text.trim().length < 2}>{busy ? "Sending…" : "Correct it"}</button>
        </div>
      </form>

      {cats.length > 0 && (
        <section class="card">
          <h2>Your mistakes, last 30 days</h2>
          <div class="chips">
            {cats.map(([k, n]) => <span key={k} class="chip chip-quiet">{data!.labels[k] ?? k} · {n}</span>)}
          </div>
        </section>
      )}

      {data && data.entries.length > 0 && (
        <ul class="jr-list">
          {data.entries.map((e) => (
            <Entry key={e.id} e={e} onRetry={() => api.journalRetry(e.id).then(load).catch((err) => toast(err.message))} />
          ))}
        </ul>
      )}
      {data && data.entries.length === 0 && (
        <p class="muted">Write two or three sentences using today's words. Short and wrong is better than nothing: mistakes are what this is for.</p>
      )}
    </main>
  );
}
