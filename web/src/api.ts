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
  sentences?: { zh: string; en: string }[];
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
  generate: (b: { topic: string; genre: string; length: string; targets: string[] }) => post<TextDoc>("/texts/generate", b),
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
  due: (limit = 100) => req<DueCard[]>(`/reviews/due?limit=${limit}`),
  sync: (reviews: unknown[]) =>
    post<{ applied: string[]; duplicates: string[]; replayed_cards: number[] }>("/reviews", reviews),
  progress: () => req<Progress>("/progress"),
};
