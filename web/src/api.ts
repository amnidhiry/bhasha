// Typed client for the bhasha API. Same origin: the backend serves this app.

export type Status = "new" | "learning" | "known" | "ignored" | null;

export interface Syllable {
  text: string;
  citation: string;
  surface: string;
  citation_display: string;
  surface_display: string;
}

export interface Tok {
  position: number;
  sentence_index: number;
  surface: string;
  kind: "word" | "proper" | "number" | "punct" | "other";
  unit_id: number | null;
  status: Status;
  show_reading: boolean;
  syllables: Syllable[];
}

export interface TextMeta {
  title_en?: string;
  sentences?: { zh: string; en: string; id?: number; url?: string }[];
  attribution?: string;
  sentence_map?: number[];
  questions?: { question_zh: string; question_en: string; answer_en: string }[];
  targets?: string[];
  new_words?: string[];
  accepted_with_issues?: boolean;
  out_of_bounds?: string[];
  flags?: { sentence: number; note: string }[];
  level?: string;
  genre?: string;
}

export interface LlmStatus {
  connected: boolean;
  kind?: "chatgpt" | "openai_compatible";
  label?: string;
  email?: string | null;
  model?: string | null;
  base_url?: string;
  calls_today: number;
  daily_cap: number;
  secret_key_set: boolean;
}

export interface Job {
  id: number;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  params: { topic?: string; genre?: string; length?: string; targets?: string[] };
  result: { text_id?: number; title?: string };
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface TextDoc {
  id: number;
  title: string;
  provenance: string;
  meta: TextMeta;
  coverage_at_creation: number | null;
  coverage_now: number | null;
  finished_at: string | null;
  tokens: Tok[];
}

export interface TextSummary {
  id: number;
  title: string;
  provenance: string;
  coverage_at_creation: number | null;
  created_at: string;
  finished_at: string | null;
}

export interface Lookup {
  query: string;
  reading: { citation: string; citation_display: string; surface_display: string };
  units: {
    id: number;
    reading: string;
    reading_display: string;
    traditional: string | null;
    level_tags: string[];
    classifiers: string[];
    meanings: string[];
    pos: string[];
  }[];
  cedict: { traditional: string; pinyin: string; pinyin_display: string; glosses: string[] }[];
  characters: {
    character: string;
    definition?: string | null;
    pinyin?: string[];
    decomposition?: string | null;
    radical?: string | null;
    etymology?: { type?: string; hint?: string; semantic?: string; phonetic?: string } | null;
  }[];
  attribution: string;
  logged: string | null;
  frequency: { rank: number; per_million: number } | null;
  examples: Example[];
}

export interface Example {
  id: number;
  text: string;
  translation: string;
  coverage: number | null;
  source: string;
  url: string;
}

export interface FsrsState {
  state: number; // 1 learning, 2 review, 3 relearning
  step: number | null;
  stability: number | null;
  difficulty: number | null;
  due: string;
  last_review: string | null;
  lapses: number;
}

export interface SchedulerParams {
  version: string;
  weights: number[];
  desired_retention: number;
  learning_steps_minutes: number[];
  relearning_steps_minutes: number[];
  maximum_interval: number;
}

export interface DueCard {
  card_id: number;
  unit_id: number;
  facet: "meaning" | "reading" | "listening" | string;
  headword: string;
  reading: string;
  reading_display: string;
  meanings: string[];
  classifiers: string[];
  context_sentence: string | null;
  due: string;
  is_new: boolean;
  leech: boolean;
  retrievability: number;
  fsrs: FsrsState;
}

export interface HandwritingOverview {
  bands: { band: string; total: number; practising: number; written: number }[];
  own_characters: number;
  cards: number;
}

export interface DrillItem {
  drill: string;
  item: string;
  prompt: string;
  audio: import("./audio").AudioSpec;
  options: { value: string; label: string; audio?: import("./audio").AudioSpec }[] | null;
  answer: string;
  reveal: string;
}

export interface Bootcamp {
  tones: { tone: number; name: string; chao: number[]; mark: string; how: string; english: string; pitfall: string }[];
  tone_examples: { key: string; label: string; char: string }[];
  initial_groups: { id: string; initials: string[]; examples: string[]; tip: string; audio: { key: string; label: string; char: string }[] }[];
  final_notes: { id: string; title: string; body: string }[];
  drills: { id: string; title: string; about: string; group?: string; attempts: number; accuracy: number | null; mastered: boolean }[];
  tone_accuracy: Record<string, number | null>;
  recorded_audio: boolean;
  mastery: { window: number; accuracy: number };
}

export interface FsrsStatus {
  personalized: boolean;
  fitted_at: string | null;
  desired_retention: number;
  retention_is_default: boolean;
  suggested_retention: number | null;
  reviews: number;
  min_reviews: number;
  fit_due: string | null;
  fit_running: boolean;
  history: {
    id: number;
    status: "accepted" | "rejected" | "skipped" | "failed";
    message: string;
    n_reviews: number;
    metrics: { holdout_current?: { log_loss: number | null; rmse_bins: number | null; n: number }; holdout_fitted?: { log_loss: number | null; rmse_bins: number | null; n: number } };
    optimal_retention: number | null;
    created_at: string;
  }[];
}

export interface ToneCheck {
  voice: string;
  accuracy: number | null;
  n: number;
  per_tone: Record<string, number | null>;
  misses: { key: string; char: string; tone: number; heard: number | null }[];
  at: string;
  engine?: string;
  device?: string;
}

export interface SpeechStatus {
  hosts: { url: string; online: boolean; engine?: string; device?: string; voices?: string[] }[];
  active: string | null;
  voice: string | null;
  voices: string[];
  tone_check: Record<string, ToneCheck>;
}

export interface Progress {
  known_words: number;
  known_characters: number;
  cards: number;
  hsk_version: string;
  hsk_cumulative: { level: string; words: number; known: number; coverage: number | null }[];
  texts_finished: number;
  characters_read: number;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) => req<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  texts: () => req<TextSummary[]>("/texts"),
  text: (id: number) => req<TextDoc>(`/texts/${id}`),
  importText: (title: string, body: string) => post<TextDoc>("/texts/import", { title, body }),
  generate: (b: { topic: string; genre: string; length: string; targets: string[] }) => post<Job>("/jobs/generate", b),
  jobs: (kind?: string) => req<Job[]>(`/jobs${kind ? `?kind=${kind}` : ""}`),
  jobSeen: (id: number) => post<Job>(`/jobs/${id}/seen`, {}),
  jobRetry: (id: number) => post<Job>(`/jobs/${id}/retry`, {}),
  flag: (id: number, sentence: number, note = "") => post<{ flags: unknown[] }>(`/texts/${id}/flag`, { sentence, note }),
  llmStatus: () => req<LlmStatus>("/llm/status"),
  chatgptStart: () => post<{ flow_id: string; authorize_url: string; redirect_uri: string }>("/llm/chatgpt/start", {}),
  chatgptFinish: (flow_id: string, address: string) => post<LlmStatus>("/llm/chatgpt/finish", { flow_id, address }),
  connectCompatible: (base_url: string, api_key: string | null, model: string | null) =>
    post<LlmStatus>("/llm/openai-compatible", { base_url, api_key, model, label: "OpenAI-compatible" }),
  llmModels: () => req<{ id: string; name: string }[]>("/llm/models"),
  setModel: (model: string) => req<LlmStatus>("/llm/model", { method: "PUT", body: JSON.stringify({ model }) }),
  signOut: () => post<LlmStatus>("/llm/signout", {}),
  finish: (id: number) => post<{ exposures: number; characters_read: number }>(`/texts/${id}/finish`, {}),
  lookup: (q: string, opts: { textId?: number; log?: boolean } = {}) => {
    const p = new URLSearchParams({ q });
    if (opts.textId != null) p.set("text_id", String(opts.textId));
    if (opts.log) p.set("log", "true");
    return req<Lookup>(`/lookup?${p}`);
  },
  mine: (unitId: number, sentence: string, textId?: number) =>
    post<{ unit_id: number; created: { card_id: number; facet: string }[] }>("/mine", {
      unit_id: unitId,
      sentence,
      text_id: textId,
    }),
  mark: (unitIds: number[], status: "known" | "ignored" | "clear") =>
    post<{ marked: number }>("/units/mark", { unit_ids: unitIds, status }),
  markLevel: (levelTag: string, status: "known" | "clear") =>
    post<{ marked: number }>("/units/mark", { level_tag: levelTag, status }),
  schedulerParams: () => req<SchedulerParams>("/reviews/params"),
  due: (limit = 100, mode: "words" | "writing" = "words") => req<DueCard[]>(`/reviews/due?limit=${limit}&mode=${mode}`),
  handwriting: () => req<HandwritingOverview>("/handwriting"),
  handwritingAdd: (b: { characters?: string[]; from_list?: number; context?: string }) =>
    post<{ created: { card_id: number; character: string }[] }>("/handwriting/add", b),
  sync: (reviews: unknown[]) =>
    post<{ applied: string[]; duplicates: string[]; replayed_cards: number[] }>("/reviews", reviews),
  progress: () => req<Progress>("/progress"),
  fsrs: () => req<FsrsStatus>("/fsrs"),
  speech: () => req<SpeechStatus>("/speech"),
  speechVoice: (voice: string) => req<SpeechStatus>("/speech/voice", { method: "PUT", body: JSON.stringify({ voice }) }),
  toneCheck: (voices: string[] = []) => post<{ job_id: number }>("/speech/tone-check", { voices }),
  fsrsFit: () => post<FsrsStatus>("/fsrs/fit", {}),
  fsrsRetention: (desired_retention: number | null) =>
    req<FsrsStatus>("/fsrs/retention", { method: "PUT", body: JSON.stringify({ desired_retention }) }),
  bootcamp: () => req<Bootcamp>("/bootcamp"),
  examples: (unitId: number, limit = 3) => req<Example[]>(`/units/${unitId}/examples?limit=${limit}`),
  sentencesText: (n = 8) => post<TextDoc>("/texts/sentences", { n }),
  drill: (drill: string, n = 10) => req<DrillItem[]>(`/bootcamp/drill?drill=${encodeURIComponent(drill)}&n=${n}`),
  drillAttempt: (a: { drill: string; item: string; answer: string; correct: boolean }) => post<Bootcamp>("/bootcamp/attempts", [a]),
};
