// The language being studied, from the server's language pack (GET /api/me).
// Cached so the app renders in the right language offline and before the first
// response. Switching language reloads the app: every view refetches.

export interface LanguageMeta {
  code: string;
  name: string;
  adjective: string;
  native_name: string;
  bcp47: string;
  reading_aid: "pinyin" | "romanization";
  features: string[];
  glyphs: Record<string, string>;
  sentence_joiner: string;
  terminators: string;
  script_unit: string;
  starter: { title: string; body: string } | null;
  levels: { name: string; tag_prefix: string; levels: string[]; labels: Record<string, string> };
}

const KEY = "bhasha.language.v1";

export const MANDARIN: LanguageMeta = {
  code: "zh", name: "Mandarin Chinese", adjective: "Chinese", native_name: "中文", bcp47: "zh-CN",
  reading_aid: "pinyin", features: ["bootcamp", "characters", "handwriting", "tonecheck"],
  glyphs: { library: "读", review: "复", journal: "写", sounds: "音", progress: "进" },
  sentence_joiner: "", terminators: "。！？!?…", script_unit: "characters",
  starter: {
    title: "我的家 · My family",
    body: "我叫小明。我是学生。我家有四口人：爸爸、妈妈、姐姐和我。爸爸是医生，妈妈是老师。姐姐在北京工作。我很喜欢我的家。",
  },
  levels: { name: "HSK 3.0", tag_prefix: "hsk3-2025", levels: ["1", "2", "3", "4", "5", "6", "7"], labels: { "7": "7–9" } },
};

function load(): LanguageMeta {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...MANDARIN, ...JSON.parse(raw) } : MANDARIN;
  } catch {
    return MANDARIN;
  }
}

let current = load();

export const lang = () => current;
/** The `lang` attribute for text in the language being studied. */
export const tl = () => current.bcp47;
export const has = (feature: string) => current.features.includes(feature);
export const isPinyin = () => current.reading_aid === "pinyin";
export const readingAidName = () => (isPinyin() ? "pinyin" : "romanization");
export const levelLabel = (level: string) => current.levels.labels[level] ?? level;

/** "HSK 3" from a unit's level tags, in the pack's framework. */
export function levelTagLabel(tags: string[]): string | null {
  const { tag_prefix, name } = current.levels;
  const tag = tags.find((t) => t.startsWith(`${tag_prefix}:`));
  if (!tag) return null;
  const short = name.replace(/\s*\d+(\.\d+)?$/, ""); // "HSK 3.0" -> "HSK"
  return `${short} ${levelLabel(tag.split(":")[1])}`;
}

// What the first render depends on: when one of these changes, the app re-renders from scratch.
const renderKey = (m: LanguageMeta) => JSON.stringify([m.code, m.bcp47, m.reading_aid, [...m.features].sort(), m.glyphs]);

/** Adopt the server's answer; true when the app has to re-render for it
 * (another language, or different features), false for cache refreshes. */
export function adopt(meta: LanguageMeta): boolean {
  const next = { ...MANDARIN, ...meta };
  const changed = renderKey(next) !== renderKey(current);
  current = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    /* private mode: fine, just not cached */
  }
  return changed;
}
