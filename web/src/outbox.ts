// Offline-safe review queue. Each rating gets a client UUID and timestamp and is
// kept in localStorage until the server acknowledges it. The server is the
// source of truth and replays out-of-order history, so syncing late is safe.
// Learning steps are rescheduled locally with ts-fsrs (see scheduler.ts).

import { api, type DueCard, type SchedulerParams } from "./api";

const OUTBOX = "bhasha.outbox.v1";
const QUEUE = "bhasha.due.v1";
const WAITING = "bhasha.waiting.v1";
const PARAMS = "bhasha.fsrs-params.v1";

export interface PendingReview {
  id: string;
  card_id: number;
  rating: 1 | 2 | 3 | 4;
  reviewed_at: string;
  duration_ms: number;
  source: "queue";
}

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage full or blocked: reviews still go out online */
  }
}

export const pending = () => read<PendingReview[]>(OUTBOX, []);

export function enqueue(r: Omit<PendingReview, "id" | "source">) {
  const item: PendingReview = { ...r, id: uuid(), source: "queue" };
  write(OUTBOX, [...pending(), item]);
  void flush();
}

let flushing: Promise<number> | null = null;

/** Send queued reviews. Returns how many are still pending. */
export function flush(): Promise<number> {
  if (flushing) return flushing;
  flushing = (async () => {
    const items = pending();
    if (!items.length || !navigator.onLine) return items.length;
    try {
      const res = await api.sync(items);
      const done = new Set([...res.applied, ...res.duplicates]);
      write(OUTBOX, pending().filter((p) => !done.has(p.id)));
    } catch {
      /* offline or server down: keep for next time */
    }
    return pending().length;
  })().finally(() => {
    flushing = null;
  });
  return flushing;
}

export const cachedQueue = () => read<DueCard[]>(QUEUE, []);
export const saveQueue = (cards: DueCard[]) => write(QUEUE, cards);
/** Cards answered this session that come back after a learning step (minutes away). */
export const cachedWaiting = () => read<DueCard[]>(WAITING, []);
export const saveWaiting = (cards: DueCard[]) => write(WAITING, cards);
export const cachedParams = () => read<SchedulerParams | null>(PARAMS, null);
export const saveParams = (p: SchedulerParams) => write(PARAMS, p);

if (typeof window !== "undefined") {
  window.addEventListener("online", () => void flush());
}

/** crypto.randomUUID only exists in secure contexts (HTTPS or localhost); plain
 * http on the LAN needs this fallback. getRandomValues works everywhere. */
export function uuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
