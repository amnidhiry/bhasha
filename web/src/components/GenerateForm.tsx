import { useState } from "preact/hooks";
import { api, ApiError } from "../api";
import { go } from "../router";
import { toast } from "./Toast";

const TOPICS = ["我的家", "周末", "吃饭", "天气", "学校", "买东西", "看医生", "坐地铁"];
const GENRES = [
  { id: "story", label: "Story" },
  { id: "dialogue", label: "Dialogue" },
  { id: "everyday", label: "Everyday" },
  { id: "news", label: "News" },
] as const;
const LENGTHS = [
  { id: "short", label: "Short" },
  { id: "medium", label: "Medium" },
  { id: "long", label: "Long" },
] as const;

export function GenerateForm({ onCancel, onQueued }: { onCancel: () => void; onQueued: () => void }) {
  const [topic, setTopic] = useState("");
  const [genre, setGenre] = useState<string>("story");
  const [length, setLength] = useState<string>("short");
  const [targets, setTargets] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: Event) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.generate({
        topic, genre, length,
        targets: targets.split(/[\s,，、]+/).filter(Boolean).slice(0, 5),
      });
      toast("Writing your text. Keep reading or reviewing; it'll show up here.");
      onQueued();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast("Connect a model first: Progress → Text generation");
        go("#/progress");
      } else {
        toast((err as Error).message);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form class="card form" onSubmit={submit} aria-busy={busy}>
      <label>
        <span>Topic</span>
        <input lang="zh-CN" value={topic} onInput={(e) => setTopic(e.currentTarget.value)} placeholder="Anything, in English or Chinese" />
      </label>
      <div class="chips" role="list">
        {TOPICS.map((t) => (
          <button type="button" key={t} lang="zh-CN" class={`chip-btn ${topic === t ? "on" : ""}`} onClick={() => setTopic(t)}>{t}</button>
        ))}
      </div>
      <div class="form-row">
        <div class="seg" role="radiogroup" aria-label="Kind">
          {GENRES.map((g) => (
            <button type="button" key={g.id} role="radio" aria-checked={genre === g.id} class={genre === g.id ? "on" : ""}
              onClick={() => setGenre(g.id)}>{g.label}</button>
          ))}
        </div>
        <div class="seg" role="radiogroup" aria-label="Length">
          {LENGTHS.map((l) => (
            <button type="button" key={l.id} role="radio" aria-checked={length === l.id} class={length === l.id ? "on" : ""}
              onClick={() => setLength(l.id)}>{l.label}</button>
          ))}
        </div>
      </div>
      <label>
        <span>Words to practise <em class="muted">(optional; otherwise your recent and due words)</em></span>
        <input lang="zh-CN" value={targets} onInput={(e) => setTargets(e.currentTarget.value)} placeholder="银行 医生" />
      </label>
      <div class="form-foot">
        <span class="muted">Written at your level, then checked word by word. Takes about a minute in the background.</span>
        <span class="row tight">
          <button type="button" class="btn quiet" onClick={onCancel} disabled={busy}>Cancel</button>
          <button class="btn primary" disabled={busy}>{busy ? "Queuing…" : "Write it"}</button>
        </span>
      </div>
    </form>
  );
}
