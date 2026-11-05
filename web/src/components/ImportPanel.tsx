import { useEffect, useState } from "preact/hooks";
import {
  api, importApi,
  type EpubBook, type ImportConfig, type ImportPreview, type JellyfinItem, type JellyfinSubtitle,
} from "../api";
import { go } from "../router";
import { toast } from "./Toast";
import { num, pct } from "../format";

type Tab = "paste" | "url" | "epub" | "subtitles" | "jellyfin";

const TABS: { id: Tab; label: string }[] = [
  { id: "paste", label: "Paste" },
  { id: "url", label: "Link" },
  { id: "epub", label: "Book" },
  { id: "subtitles", label: "Subtitles" },
  { id: "jellyfin", label: "Jellyfin" },
];

/** How a coverage figure reads: ~95% known is where unassisted reading starts. */
function readability(c: number | null): { label: string; cls: string } {
  if (c == null) return { label: "No words to score", cls: "chip-quiet" };
  if (c >= 0.95) return { label: "Comfortable", cls: "status-known" };
  if (c >= 0.85) return { label: "A stretch", cls: "chip-warn" };
  return { label: "Hard going", cls: "" };
}

export function ImportPanel({ onCancel }: { onCancel: () => void }) {
  const [config, setConfig] = useState<ImportConfig | null>(null);
  const [tab, setTab] = useState<Tab>("paste");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    importApi.config().then(setConfig).catch(() => setConfig(null));
  }, []);

  const tabs = TABS.filter((t) => t.id !== "jellyfin" || config?.jellyfin);

  async function run(p: Promise<ImportPreview>) {
    setBusy(true);
    try {
      setPreview(await p);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (preview) {
    return <PreviewCard preview={preview} onBack={() => setPreview(null)} />;
  }

  return (
    <section class="card form import" aria-busy={busy}>
      <div class="seg import-tabs" role="tablist" aria-label="Import from">
        {tabs.map((t) => (
          <button type="button" key={t.id} role="tab" aria-selected={tab === t.id} class={tab === t.id ? "on" : ""}
            onClick={() => setTab(t.id)}>{t.label}</button>
        ))}
      </div>
      {tab === "paste" && <PasteForm onCancel={onCancel} />}
      {tab === "url" && <LinkForm busy={busy} onPreview={(u) => run(importApi.url(u))} onCancel={onCancel} />}
      {tab === "epub" && <BookForm busy={busy} setBusy={setBusy} onPreview={run} onCancel={onCancel} />}
      {tab === "subtitles" && <SubtitleForm busy={busy} onPreview={(f, t) => run(importApi.subtitles(f, t))} onCancel={onCancel} />}
      {tab === "jellyfin" && <JellyfinForm busy={busy} setBusy={setBusy} onPreview={run} onCancel={onCancel} />}
    </section>
  );
}

function Foot({ note, busy, label, disabled, onCancel }: {
  note: string; busy: boolean; label: string; disabled?: boolean; onCancel: () => void;
}) {
  return (
    <div class="form-foot">
      <span class="muted">{note}</span>
      <span class="row tight">
        <button type="button" class="btn quiet" onClick={onCancel} disabled={busy}>Cancel</button>
        <button class="btn primary" disabled={busy || disabled}>{busy ? "Reading…" : label}</button>
      </span>
    </div>
  );
}

function PasteForm({ onCancel }: { onCancel: () => void }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: Event) {
    e.preventDefault();
    if (!body.trim()) return;
    setBusy(true);
    try {
      const doc = await api.importText(title.trim() || body.trim().slice(0, 12), body);
      go(`#/read/${doc.id}`);
    } catch (err) {
      toast(`Import failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form class="form" onSubmit={submit}>
      <label>
        <span>Title</span>
        <input value={title} onInput={(e) => setTitle(e.currentTarget.value)} placeholder="Optional" />
      </label>
      <label>
        <span>Chinese text</span>
        <textarea lang="zh-CN" rows={7} value={body} onInput={(e) => setBody(e.currentTarget.value)}
          placeholder="Paste an article, dialogue or subtitles…" required />
      </label>
      <Foot note="You'll see how much of it you already know before you start." busy={busy} label="Add"
        disabled={!body.trim()} onCancel={onCancel} />
    </form>
  );
}

function LinkForm({ busy, onPreview, onCancel }: { busy: boolean; onPreview: (u: string) => void; onCancel: () => void }) {
  const [url, setUrl] = useState("");
  return (
    <form class="form" onSubmit={(e) => { e.preventDefault(); if (url.trim()) onPreview(url.trim()); }}>
      <label>
        <span>Web page</span>
        <input type="url" inputMode="url" autoComplete="off" value={url} onInput={(e) => setUrl(e.currentTarget.value)}
          placeholder="https://…" required />
      </label>
      <Foot note="Keeps the article text: no menus, ads or comments." busy={busy} label="Preview"
        disabled={!url.trim()} onCancel={onCancel} />
    </form>
  );
}

function FilePick({ accept, file, onFile, hint }: { accept: string; file: File | null; onFile: (f: File) => void; hint: string }) {
  return (
    <label class="file-pick">
      <input type="file" accept={accept} onChange={(e) => { const f = e.currentTarget.files?.[0]; if (f) onFile(f); }} />
      <span class="btn">{file ? "Choose another" : "Choose file"}</span>
      <span class="file-name muted">{file ? file.name : hint}</span>
    </label>
  );
}

function BookForm({ busy, setBusy, onPreview, onCancel }: {
  busy: boolean; setBusy: (b: boolean) => void; onPreview: (p: Promise<ImportPreview>) => void; onCancel: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [book, setBook] = useState<EpubBook | null>(null);
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(0);

  async function choose(f: File) {
    setFile(f);
    setBook(null);
    setBusy(true);
    try {
      const b = await importApi.epubChapters(f);
      setBook(b);
      setStart(0);
      setEnd(0);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const chars = book ? book.chapters.slice(start, end + 1).reduce((n, c) => n + c.characters, 0) : 0;

  return (
    <form class="form" onSubmit={(e) => { e.preventDefault(); if (file && book) onPreview(importApi.epub(file, start, end)); }}>
      <FilePick accept=".epub,application/epub+zip" file={file} onFile={choose} hint="An .epub book" />
      {book && (
        <>
          <p class="book-head">
            <span class="text-title" lang="zh-CN">{book.title}</span>
            {book.author && <span class="muted small" lang="zh-CN"> · {book.author}</span>}
            <span class="muted small"> · {book.chapters.length} chapters</span>
          </p>
          <div class="form-row two">
            <label>
              <span>From</span>
              <select lang="zh-CN" value={start} onChange={(e) => {
                const s = Number(e.currentTarget.value);
                setStart(s);
                if (end < s) setEnd(s);
              }}>
                {book.chapters.map((c) => <option key={c.index} value={c.index}>{c.title}</option>)}
              </select>
            </label>
            <label>
              <span>To</span>
              <select lang="zh-CN" value={end} onChange={(e) => setEnd(Number(e.currentTarget.value))}>
                {book.chapters.filter((c) => c.index >= start).map((c) => <option key={c.index} value={c.index}>{c.title}</option>)}
              </select>
            </label>
          </div>
          {start === end && book.chapters[start] && (
            <p class="excerpt" lang="zh-CN">{book.chapters[start].excerpt}…</p>
          )}
        </>
      )}
      <Foot note={book ? `${num(chars)} characters selected.` : "Pick a chapter, or a run of chapters, to read as one text."}
        busy={busy} label="Preview" disabled={!book} onCancel={onCancel} />
    </form>
  );
}

function SubtitleForm({ busy, onPreview, onCancel }: {
  busy: boolean; onPreview: (f: File, title: string) => void; onCancel: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  return (
    <form class="form" onSubmit={(e) => { e.preventDefault(); if (file) onPreview(file, title.trim()); }}>
      <FilePick accept=".srt,.vtt,text/vtt,application/x-subrip" file={file} onFile={setFile} hint="An .srt or .vtt file" />
      <label>
        <span>Title</span>
        <input lang="zh-CN" value={title} onInput={(e) => setTitle(e.currentTarget.value)} placeholder="Optional; the file name otherwise" />
      </label>
      <Foot note="Timestamps go; bilingual files keep the Chinese lines. Long files become parts."
        busy={busy} label="Preview" disabled={!file} onCancel={onCancel} />
    </form>
  );
}

function JellyfinForm({ busy, setBusy, onPreview, onCancel }: {
  busy: boolean; setBusy: (b: boolean) => void; onPreview: (p: Promise<ImportPreview>) => void; onCancel: () => void;
}) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<JellyfinItem[] | null>(null);
  const [series, setSeries] = useState<JellyfinItem | null>(null);
  const [item, setItem] = useState<{ id: string; name: string; subtitles: JellyfinSubtitle[] } | null>(null);

  async function load<T>(p: Promise<T>, then: (v: T) => void) {
    setBusy(true);
    try {
      then(await p);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const search = (e: Event) => {
    e.preventDefault();
    if (!q.trim()) return;
    setSeries(null);
    setItem(null);
    void load(importApi.jellyfinSearch(q.trim()), setItems);
  };
  const open = (it: JellyfinItem) => {
    if (it.type === "Series") {
      void load(importApi.jellyfinEpisodes(it.id), (eps) => { setSeries(it); setItems(eps); });
    } else {
      void load(importApi.jellyfinSubtitles(it.id), setItem);
    }
  };

  if (item) {
    return (
      <div class="form">
        <button type="button" class="link-btn" onClick={() => setItem(null)}>‹ Back</button>
        <p class="text-title" lang="zh-CN">{item.name}</p>
        {item.subtitles.length === 0 && <p class="muted">This has no subtitle tracks.</p>}
        <ul class="pick-list">
          {item.subtitles.map((s) => (
            <li key={`${s.media_source_id}:${s.index}`}>
              <button type="button" class="pick-row" disabled={busy || !s.text}
                onClick={() => onPreview(importApi.jellyfin(item.id, s.index, s.media_source_id))}>
                <span>{s.title}</span>
                <span class="text-meta">
                  {s.chinese && <span class="chip">Chinese</span>}
                  {s.external && <span class="chip chip-quiet">file</span>}
                  {!s.text && <span class="chip chip-quiet">image, can't read</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <form class="form" onSubmit={search}>
      <label>
        <span>Search your library</span>
        <input type="search" lang="zh-CN" value={q} onInput={(e) => setQ(e.currentTarget.value)} placeholder="A film, series or episode" />
      </label>
      {series && (
        <p class="muted small">
          <button type="button" class="link-btn" onClick={() => { setSeries(null); void load(importApi.jellyfinSearch(q.trim()), setItems); }}>
            ‹ Results
          </button>{" "}
          <span lang="zh-CN">{series.name}</span>
        </p>
      )}
      {items && items.length === 0 && <p class="muted">Nothing found.</p>}
      {items && items.length > 0 && (
        <ul class="pick-list">
          {items.map((it) => (
            <li key={it.id}>
              <button type="button" class="pick-row" disabled={busy} onClick={() => open(it)}>
                <span lang="zh-CN">{it.name}</span>
                <span class="text-meta">
                  {it.type === "Series" ? <span class="chip chip-quiet">series ›</span>
                    : it.chinese_subtitles ? <span class="chip">中文 subtitles</span>
                    : it.chinese_subtitles === 0 ? <span class="chip chip-quiet">no Chinese subtitles</span> : null}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <Foot note="Subtitles from your Jellyfin server, read as text." busy={busy} label="Search"
        disabled={!q.trim()} onCancel={onCancel} />
    </form>
  );
}

function PreviewCard({ preview, onBack }: { preview: ImportPreview; onBack: () => void }) {
  const [title, setTitle] = useState(preview.title);
  const [busy, setBusy] = useState(false);
  const multi = preview.parts.length > 1;
  const r = readability(preview.coverage);

  async function add() {
    setBusy(true);
    try {
      const t = title.trim() || preview.title;
      const n = preview.parts.length;
      const parts = preview.parts.map((p, i) => ({ title: multi ? `${t} (${i + 1}/${n})` : t, body: p.body }));
      const res = await importApi.save({ kind: preview.kind, source_url: preview.source_url, meta: preview.meta, parts });
      if (multi) toast(`Added ${n} parts`);
      go(`#/read/${res.texts[0].id}`);
    } catch (e) {
      toast(`Import failed: ${(e as Error).message}`);
      setBusy(false);
    }
  }

  return (
    <section class="card form import-preview" aria-busy={busy}>
      <label>
        <span>Title</span>
        <input lang="zh-CN" value={title} onInput={(e) => setTitle(e.currentTarget.value)} />
      </label>
      <div class="cov-line">
        <span class="cov-big">{pct(preview.coverage)} known</span>
        <span class="muted"> · {num(preview.characters)} characters</span>
        {preview.new_words > 0 && <span class="muted"> · {num(preview.new_words)} new words</span>}
      </div>
      <div class="text-meta">
        <span class={`chip ${r.cls}`}>{r.label}</span>
        {preview.warnings.map((w) => <span key={w} class="chip chip-warn">{w}</span>)}
      </div>
      {preview.source_url && !preview.source_url.startsWith("jellyfin") && (
        <p class="muted small source">{preview.source_url}</p>
      )}
      {multi ? (
        <ol class="parts">
          {preview.parts.map((p, i) => (
            <li key={i}>
              <span lang="zh-CN" class="part-excerpt">{p.body.slice(0, 24)}…</span>
              <span class="muted small">{pct(p.coverage)} · {num(p.characters)}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p class="excerpt" lang="zh-CN">{preview.parts[0]?.body.slice(0, 140)}{(preview.parts[0]?.body.length ?? 0) > 140 ? "…" : ""}</p>
      )}
      <div class="form-foot">
        <span class="muted">{multi ? `Saved as ${preview.parts.length} texts of about 1,500 characters.` : "Words you meet here can go to your reviews."}</span>
        <span class="row tight">
          <button type="button" class="btn quiet" onClick={onBack} disabled={busy}>Back</button>
          <button type="button" class="btn primary" onClick={add} disabled={busy}>
            {busy ? "Adding…" : multi ? `Add ${preview.parts.length}` : "Add"}
          </button>
        </span>
      </div>
    </section>
  );
}
