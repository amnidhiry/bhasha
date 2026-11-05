import { isPinyin } from "../lang";
import { useSettings } from "../settings";
import { syllablePairs } from "../tones";

/** The reading aid: pinyin with optional per-tone color (a learning aid, toggled in
 * settings), or a plain romanization for languages without tones. */
export function Pinyin({ numeric, display, class: cls = "" }: { numeric: string; display: string; class?: string }) {
  const { toneColors } = useSettings();
  if (!isPinyin()) return <span class={`romanization ${cls}`}>{display}</span>;
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
