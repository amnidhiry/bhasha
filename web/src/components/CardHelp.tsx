import { tl } from "../lang";
import { useEffect, useState } from "preact/hooks";
import { api, type CardHelp as Help } from "../api";
import { speak } from "../speech";
import { toast } from "./Toast";

/** For cards that keep slipping: the parts, a mnemonic from the real components,
 * fresh examples, or suspending the card. */
export function CardHelp({ cardId, onSuspended }: { cardId: number; onSuspended: () => void }) {
  const [h, setH] = useState<Help | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => void api.cardHelp(cardId).then(setH).catch((e) => toast(e.message)), [cardId]);
  if (!h) return <p class="muted small">Loading help…</p>;

  async function mnemonic() {
    setBusy(true);
    try {
      const r = await api.cardMnemonic(cardId);
      setH({ ...h!, mnemonic: r.mnemonic });
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div class="card-help" onClick={(e) => e.stopPropagation()}>
      {h.characters.map((c) => (
        <div key={c.char} class="ch-row">
          <a class="ch-glyph" lang={tl()} href={`#/char/${encodeURIComponent(c.char)}`}>{c.char}</a>
          <div>
            <p class="small"><b>{c.reading}</b> {c.definition}</p>
            {c.parts.length > 0 && (
              <p class="small">
                {c.parts.map((p, i) => (
                  <span key={i} class="ch-part">
                    <span lang={tl()}>{p.part}</span> {p.meaning ?? ""}
                    {p.role && <span class={`chip ${p.role === "meaning" ? "" : "chip-quiet"}`}>{p.role}</span>}
                  </span>
                ))}
              </p>
            )}
            {c.notes.slice(0, 2).map((n, i) => <p key={i} class="muted small">{n}</p>)}
          </div>
        </div>
      ))}
      {h.mnemonic ? (
        <p class="mnemonic">{h.mnemonic}</p>
      ) : (
        <button class="btn" disabled={busy} onClick={mnemonic}>{busy ? "Writing…" : "Make a mnemonic"}</button>
      )}
      {h.examples.map((e) => (
        <p key={e.id} class="small">
          <span lang={tl()} class="ex-zh-inline" onClick={() => speak(e.text)}>{e.text}</span> {e.translation}
        </p>
      ))}
      <button class="link-btn" onClick={() => api.cardSuspend(cardId).then(() => { toast("Suspended. It won't come up until you unsuspend it."); onSuspended(); })}>
        Suspend this card
      </button>
    </div>
  );
}
