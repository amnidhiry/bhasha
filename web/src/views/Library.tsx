import { useEffect, useState } from "preact/hooks";
import { api, type TextSummary } from "../api";
import { go } from "../router";
import { GenerateForm } from "../components/GenerateForm";
import { toast } from "../components/Toast";
import { pct } from "../format";

const STARTER = {
  title: "我的家 · My family",
  body: "我叫小明。我是学生。我家有四口人：爸爸、妈妈、姐姐和我。爸爸是医生，妈妈是老师。姐姐在北京工作。我很喜欢我的家。",
};

export function Library() {
  const [texts, setTexts] = useState<TextSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.texts().then(setTexts).catch((e) => setError(e.message));
  }, []);

  async function importText(t: string, b: string) {
    setBusy(true);
    try {
      const doc = await api.importText(t.trim() || b.trim().slice(0, 12), b);
      go(`#/read/${doc.id}`);
    } catch (e) {
      toast(`Import failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main class="page">
      <header class="page-head">
        <h1>Read</h1>
        <span class="row tight">
          <button class="btn" onClick={() => { setAdding((a) => !a); setGenerating(false); }} aria-expanded={adding}>
            {adding ? "Cancel" : "Paste"}
          </button>
          <button class="btn primary" onClick={() => { setGenerating((g) => !g); setAdding(false); }} aria-expanded={generating}>
            Write me a text
          </button>
        </span>
      </header>

      {adding && (
        <form class="card form" onSubmit={(e) => { e.preventDefault(); if (body.trim()) void importText(title, body); }}>
          <label>
            <span>Title</span>
            <input value={title} onInput={(e) => setTitle(e.currentTarget.value)} placeholder="Optional" />
          </label>
          <label>
            <span>Chinese text</span>
            <textarea lang="zh-CN" rows={7} value={body} onInput={(e) => setBody(e.currentTarget.value)}
              placeholder="Paste an article, dialogue or subtitles…" required />
          </label>
          <div class="form-foot">
            <span class="muted">You'll see how much of it you already know before you start.</span>
            <button class="btn primary" disabled={busy || !body.trim()}>{busy ? "Reading…" : "Add"}</button>
          </div>
        </form>
      )}

      {generating && <GenerateForm onCancel={() => setGenerating(false)} />}

      {error && <p class="error">Can't reach the server: {error}</p>}
      {texts && texts.length === 0 && !adding && !generating && (
        <section class="empty card">
          <p class="empty-glyph" lang="zh-CN" aria-hidden="true">读</p>
          <h2>Start with a short text</h2>
          <p class="muted">
            Tap any word to hear it, see its tones and parts, and add it to your reviews. Words enter review only after
            you've met them in a sentence.
          </p>
          <button class="btn primary" disabled={busy} onClick={() => importText(STARTER.title, STARTER.body)}>
            Open a starter text
          </button>
        </section>
      )}

      {texts && texts.length > 0 && (
        <ul class="text-list">
          {texts.map((t) => (
            <li key={t.id}>
              <a class="text-row card" href={`#/read/${t.id}`}>
                <span class="text-title" lang="zh-CN">{t.title}</span>
                <span class="text-meta">
                  {t.coverage_at_creation != null && <span>{pct(t.coverage_at_creation)} known when added</span>}
                  {t.provenance !== "imported" && <span class="chip chip-quiet">{t.provenance}</span>}
                  {t.finished_at && <span class="done" aria-label="finished">✓ read</span>}
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
      {!texts && !error && <p class="muted">Loading…</p>}
    </main>
  );
}
