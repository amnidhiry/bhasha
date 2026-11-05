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
  retention_by_facet?: Record<string, number>;
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
  cloze?: { sentence: string; answer: string; wrong: string; category: string; explanation: string; english: string } | null;
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
  retention_by_facet: Record<string, number>;
  reading_first: boolean;
  backlog_threshold: number;
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

export interface JournalEntry {
  id: number;
  text: string;
  status: "queued" | "done" | "failed";
  corrected: string | null;
  comment: string | null;
  error: string | null;
  prompt: { words?: string[]; idea?: string };
  created_at: string;
  sentences: { original: string; corrected: string; english: string }[];
  errors: { id: number; category: string; label: string; wrong: string; right: string; explanation: string;
    sentence_index: number; card_id: number | null }[];
}

export interface TutorScenario { id: string; title: string; title_zh: string; setting: string; goal: string; role: string; completed?: number }

export interface TutorTurn {
  id: number;
  role: "tutor" | "learner";
  text: string;
  english: string | null;
  tokens?: Tok[];
  hint?: string | null;
  off_level?: string[];
  corrected?: string | null;
  errors?: { category: string; label: string; wrong: string; right: string; explanation: string; card_id: number | null }[];
}

export interface TutorSession {
  id: number;
  scenario: TutorScenario;
  status: "active" | "ended";
  goal_met: boolean;
  turns: TutorTurn[];
  mistakes: number;
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

export type Transparency = "clear" | "partial" | "opaque" | "unknown";
export type CharStatus = "known" | "learning" | "new";

export interface CharSummary {
  character: string;
  pinyin: string[];
  definition: string | null;
  status: CharStatus;
  frequency_rank: number | null;
  transparency: Transparency;
}

export interface ComponentFamily {
  key: string;
  members: string[];
  definition: string | null;
  pinyin: string[];
}

export interface CharNote {
  kind: string;
  component: string | null;
  text: string;
  match?: string;
}

export interface CharWord {
  unit_id: number;
  headword: string;
  reading_display: string;
  meanings: string[];
  status: CharStatus;
}

export interface CharacterPage extends CharSummary {
  decomposition: string | null;
  radical: string | null;
  radical_family: string | null;
  etymology: { type?: string; hint?: string; semantic?: string; phonetic?: string } | null;
  parts: {
    component: string;
    family: string;
    members: string[];
    definition: string | null;
    gloss: string | null;
    pinyin: string[];
    role: "meaning" | "sound" | null;
    decomposition: string | null;
    yours: number;
  }[];
  frequency: { rank: number; per_million: number } | null;
  notes: CharNote[];
  words: CharWord[];
  more_words: CharWord[];
  has_strokes: boolean;
  writing: boolean;
  attribution: string;
}

export interface ComponentResult {
  component: string;
  family: ComponentFamily;
  counts: { total: number; known: number; learning: number };
  characters: (CharSummary & { depth: number; via: string | null })[];
  filtered: boolean;
  attribution: string;
}

export interface CharactersOverview {
  counts: { known: number; learning: number };
  characters: CharSummary[];
  groups: (ComponentFamily & { count: number; characters: string[] })[];
  attribution: string;
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
  tutorScenarios: () => req<TutorScenario[]>("/tutor/scenarios"),
  tutorSessions: () => req<{ id: number; scenario: TutorScenario; status: string; goal_met: boolean; created_at: string }[]>("/tutor/sessions"),
  tutorStart: (scenario: string) => post<TutorSession>("/tutor/sessions", { scenario }),
  tutorSession: (id: number) => req<TutorSession>(`/tutor/sessions/${id}`),
  tutorSay: (id: number, text: string) => post<TutorSession>(`/tutor/sessions/${id}/turns`, { text }),
  tutorEnd: (id: number) => post<TutorSession>(`/tutor/sessions/${id}/end`, {}),
  journalPrompt: () => req<{ words: string[]; idea: string }>("/journal/prompt"),
  journal: () => req<{ entries: JournalEntry[]; categories: Record<string, number>; labels: Record<string, string> }>("/journal"),
  journalEntry: (id: number) => req<JournalEntry>(`/journal/${id}`),
  journalWrite: (text: string, prompt: object) => post<JournalEntry>("/journal", { text, prompt }),
  journalRetry: (id: number) => post<JournalEntry>(`/journal/${id}/retry`, {}),
  speech: () => req<SpeechStatus>("/speech"),
  speechVoice: (voice: string) => req<SpeechStatus>("/speech/voice", { method: "PUT", body: JSON.stringify({ voice }) }),
  toneCheck: (voices: string[] = []) => post<{ job_id: number }>("/speech/tone-check", { voices }),
  fsrsFit: () => post<FsrsStatus>("/fsrs/fit", {}),
  fsrsFacetRetention: (facet: string, desired_retention: number | null) =>
    req<FsrsStatus>("/fsrs/retention", { method: "PUT", body: JSON.stringify({ facet, desired_retention }) }),
  fsrsReadingFirst: (enabled: boolean, threshold: number) =>
    req<FsrsStatus>("/fsrs/reading-first", { method: "PUT", body: JSON.stringify({ enabled, threshold }) }),
  reviewStatus: (mode: "words" | "writing") =>
    req<{ backlog: number; threshold: number; reading_first: boolean; new_paused: boolean }>(`/reviews/status?mode=${mode}`),
  fsrsRetention: (desired_retention: number | null) =>
    req<FsrsStatus>("/fsrs/retention", { method: "PUT", body: JSON.stringify({ desired_retention }) }),
  bootcamp: () => req<Bootcamp>("/bootcamp"),
  characters: () => req<CharactersOverview>("/characters"),
  character: (ch: string) => req<CharacterPage>(`/characters/${encodeURIComponent(ch)}`),
  component: (c: string, opts: { all?: boolean; direct?: boolean } = {}) =>
    req<ComponentResult>(`/components/${encodeURIComponent(c)}?all=${!!opts.all}&direct=${!!opts.direct}`),
  examples: (unitId: number, limit = 3) => req<Example[]>(`/units/${unitId}/examples?limit=${limit}`),
  sentencesText: (n = 8) => post<TextDoc>("/texts/sentences", { n }),
  drill: (drill: string, n = 10) => req<DrillItem[]>(`/bootcamp/drill?drill=${encodeURIComponent(drill)}&n=${n}`),
  drillAttempt: (a: { drill: string; item: string; answer: string; correct: boolean }) => post<Bootcamp>("/bootcamp/attempts", [a]),
};

// --- Importer (links, EPUB, subtitles, Jellyfin) ---------------------------

export interface ImportConfig {
  sources: string[];
  jellyfin: boolean;
  max_url_bytes: number;
  max_epub_bytes: number;
  max_subtitle_bytes: number;
  part_characters: number;
}

export interface ImportPart {
  title: string;
  body: string;
  characters: number;
  coverage: number | null;
  new_words: number;
}

/** A text scored against what you know, not saved yet. */
export interface ImportPreview {
  kind: string;
  title: string;
  source_url: string | null;
  meta: Record<string, unknown>;
  warnings: string[];
  characters: number;
  coverage: number | null;
  new_words: number;
  parts: ImportPart[];
}

export interface EpubChapter {
  index: number;
  title: string;
  characters: number;
  excerpt: string;
}

export interface EpubBook {
  title: string;
  author: string | null;
  chapters: EpubChapter[];
}

export interface JellyfinItem {
  id: string;
  name: string;
  type: string; // Movie | Episode | Series
  chinese_subtitles?: number | null;
}

export interface JellyfinSubtitle {
  index: number;
  media_source_id: string;
  language: string | null;
  title: string;
  codec: string | null;
  external: boolean;
  default: boolean;
  chinese: boolean;
  text: boolean;
}

/** Multipart upload: the browser sets the boundary, so no JSON content type. */
async function upload<T>(path: string, fields: Record<string, string | Blob>): Promise<T> {
  const form = new FormData();
  for (const [k, v] of Object.entries(fields)) form.append(k, v);
  const res = await fetch(`/api${path}`, { method: "POST", body: form });
  if (!res.ok) {
    let msg = res.status === 413 ? "That file is too large." : res.statusText;
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

export const importApi = {
  config: () => req<ImportConfig>("/import/config"),
  url: (url: string) => post<ImportPreview>("/import/url/preview", { url }),
  epubChapters: (file: File) => upload<EpubBook>("/import/epub/chapters", { file }),
  epub: (file: File, start: number, end: number) =>
    upload<ImportPreview>("/import/epub/preview", { file, start: String(start), end: String(end) }),
  subtitles: (file: File, title = "") => upload<ImportPreview>("/import/subtitles/preview", { file, title }),
  jellyfinSearch: (q: string) => req<JellyfinItem[]>(`/import/jellyfin/search?q=${encodeURIComponent(q)}`),
  jellyfinEpisodes: (seriesId: string) =>
    req<JellyfinItem[]>(`/import/jellyfin/series/${encodeURIComponent(seriesId)}/episodes`),
  jellyfinSubtitles: (itemId: string) =>
    req<{ id: string; name: string; subtitles: JellyfinSubtitle[] }>(
      `/import/jellyfin/items/${encodeURIComponent(itemId)}/subtitles`),
  jellyfin: (item_id: string, index: number, media_source_id: string) =>
    post<ImportPreview>("/import/jellyfin/preview", { item_id, index, media_source_id }),
  save: (p: { kind: string; source_url: string | null; meta: Record<string, unknown>; parts: { title: string; body: string }[] }) =>
    post<{ texts: { id: number; title: string; coverage_at_creation: number | null }[] }>("/import/texts", p),
};
