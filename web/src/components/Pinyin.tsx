import { useSettings } from "../settings";
import { syllablePairs } from "../tones";

/** Pinyin with optional per-tone color (a learning aid, toggled in settings). */
export function Pinyin({ numeric, display, class: cls = "" }: { numeric: string; display: string; class?: string }) {
  const { toneColors } = useSettings();
  return (
    <span class={`pinyin ${toneColors ? "toned" : ""} ${cls}`}>
      {syllablePairs(numeric, display).map((s, i) => (
        <span key={i} class={`t${s.tone}`}>
          {i > 0 ? " " : ""}
          {s.text}
        </span>
      ))}
    </span>
  );
}
