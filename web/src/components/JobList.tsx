import { useEffect, useRef, useState } from "preact/hooks";
import { api, type Job } from "../api";
import { toast } from "./Toast";

const POLL_MS = 3000;

/** Generation jobs: running ones with a spinner, finished ones until opened or dismissed. */
export function JobList({ refreshKey, onDone }: { refreshKey: number; onDone: () => void }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [poll, setPoll] = useState(0);
  const known = useRef(new Map<number, string>());

  useEffect(() => {
    let live = true;
    let timer: number | undefined;
    const tick = async () => {
      const list = await api.jobs("generate").catch(() => null);
      if (!live || !list) return;
      for (const j of list) {
        const before = known.current.get(j.id);
        if (before && before !== j.status && (j.status === "done" || j.status === "failed")) {
          toast(j.status === "done" ? `Ready: ${j.result.title ?? "your text"}` : "A text couldn't be written");
          if (j.status === "done") onDone();
        }
        known.current.set(j.id, j.status);
      }
      setJobs(list);
      if (list.some((j) => j.status === "queued" || j.status === "running")) timer = window.setTimeout(tick, POLL_MS);
    };
    void tick();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [refreshKey, poll]);

  const dismiss = async (j: Job) => {
    await api.jobSeen(j.id).catch(() => null);
    setJobs((js) => js.filter((x) => x.id !== j.id));
  };

  if (!jobs.length) return null;
  return (
    <ul class="jobs" aria-live="polite">
      {jobs.map((j) => (
        <li key={j.id} class={`job card job-${j.status}`}>
          {j.status === "queued" || j.status === "running" ? (
            <>
              <span class="spinner" aria-hidden="true" />
              <span class="job-body">
                <b>Writing{j.params.topic ? <> about <span lang="zh-CN">{j.params.topic}</span></> : null}…</b>
                <span class="muted small">{j.status === "queued" ? "Waiting for the worker" : "Writing, then checking each word"}</span>
              </span>
            </>
          ) : j.status === "done" ? (
            <>
              <span class="job-dot" aria-hidden="true" />
              <a class="job-body" href={`#/read/${j.result.text_id}`} onClick={() => void api.jobSeen(j.id)}>
                <b lang="zh-CN">{j.result.title}</b>
                <span class="muted small">New text ready. Open it</span>
              </a>
              <button class="btn quiet" onClick={() => dismiss(j)} aria-label="Dismiss">✕</button>
            </>
          ) : (
            <>
              <span class="job-dot failed" aria-hidden="true" />
              <span class="job-body">
                <b>Couldn't write that text</b>
                <span class="muted small">{j.error}</span>
              </span>
              <span class="row tight">
                <button class="btn" onClick={async () => {
                  const nj = await api.jobRetry(j.id).catch((e) => (toast((e as Error).message), null));
                  if (!nj) return;
                  known.current.set(nj.id, "queued");
                  setJobs((js) => [nj, ...js.filter((x) => x.id !== j.id)]);
                  setPoll((n) => n + 1);
                }}>Retry</button>
                <button class="btn quiet" onClick={() => dismiss(j)} aria-label="Dismiss">✕</button>
              </span>
            </>
          )}
        </li>
      ))}
    </ul>
  );
}
