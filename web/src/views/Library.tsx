import { isPinyin, lang, tl } from "../lang";
import { useEffect, useState } from "preact/hooks";
import { api, type TextSummary } from "../api";
import { go } from "../router";
import { GenerateForm } from "../components/GenerateForm";
import { ImportPanel } from "../components/ImportPanel";
import { JobList } from "../components/JobList";
import { toast } from "../components/Toast";
import { pct } from "../format";


export function Library() {
  const [texts, setTexts] = useState<TextSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [jobsKey, setJobsKey] = useState(0);
  const [busy, setBusy] = useState(false);

  const loadTexts = () => api.texts().then(setTexts).catch((e) => setError(e.message));
  useEffect(() => void loadTexts(), []);

  async function realSentences() {
    setBusy(true);
    try {
      const doc = await api.sentencesText(8);
      go(`#/read/${doc.id}`);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

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
            {adding ? "Cancel" : "Import"}
          </button>
          <button class="btn" disabled={busy} onClick={realSentences}
            title="Real sentences by people (Tatoeba), with at most one new word each">
            Real sentences
          </button>
          <button class="btn primary" onClick={() => { setGenerating((g) => !g); setAdding(false); }} aria-expanded={generating}>
            Write me a text
          </button>
        </span>
      </header>

      {adding && <ImportPanel onCancel={() => setAdding(false)} />}

      {generating && (
        <GenerateForm onCancel={() => setGenerating(false)}
          onQueued={() => { setGenerating(false); setJobsKey((k) => k + 1); }} />
      )}
      <JobList refreshKey={jobsKey} onDone={() => void loadTexts()} />

      {error && <p class="error">Can't reach the server: {error}</p>}
      {texts && texts.length === 0 && !adding && !generating && (
        <section class="empty card">
          {lang().glyphs.library && <p class="empty-glyph" lang={tl()} aria-hidden="true">{lang().glyphs.library}</p>}
          <h2>Start with a short text</h2>
          <p class="muted">
            Tap any word to hear it, see {isPinyin() ? "its tones and parts" : "how it's said and its dictionary form"}, and add it to your reviews. Words enter review only after
            you've met them in a sentence.
          </p>
          {lang().starter && (
            <button class="btn primary" disabled={busy} onClick={() => importText(lang().starter!.title, lang().starter!.body)}>
              Open a starter text
            </button>
          )}
        </section>
      )}

      {texts && texts.length > 0 && (
        <ul class="text-list">
          {texts.map((t) => (
            <li key={t.id}>
              <a class="text-row card" href={`#/read/${t.id}`}>
                <span class="text-title" lang={tl()}>{t.title}</span>
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
