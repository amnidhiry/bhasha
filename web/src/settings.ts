import { useEffect, useState } from "preact/hooks";

export type PinyinMode = "unknown" | "all" | "none";
export interface Settings {
  pinyin: PinyinMode;
  toneColors: boolean;
  fontScale: number;
  /** Ignore finger touches on the writing pad (palm rejection). Turned on the first time a Pencil is seen. */
  pencilOnly: boolean;
}

const KEY = "bhasha.settings.v1";
const DEFAULTS: Settings = { pinyin: "unknown", toneColors: true, fontScale: 1, pencilOnly: false };

function load(): Settings {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") };
  } catch {
    return DEFAULTS;
  }
}

let current = load();
const listeners = new Set<(s: Settings) => void>();

export const getSettings = () => current;

export function setSettings(patch: Partial<Settings>) {
  current = { ...current, ...patch };
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l(current));
}

export function useSettings(): Settings {
  const [s, set] = useState(current);
  useEffect(() => {
    listeners.add(set);
    return () => void listeners.delete(set);
  }, []);
  return s;
}
