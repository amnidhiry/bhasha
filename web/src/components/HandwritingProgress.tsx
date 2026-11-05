import { useEffect, useState } from "preact/hooks";
import { api, type HandwritingOverview } from "../api";
import { toast } from "./Toast";

/** The official HSK 3.0 handwriting list, band by band. */
export function HandwritingProgress() {
  const [hw, setHw] = useState<HandwritingOverview | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.handwriting().then(setHw).catch(() => setHw(null));
  useEffect(() => void load(), []);
  if (!hw) return null;
  const total = hw.bands.reduce((n, b) => n + b.total, 0);

  async function add(n: number) {
    setBusy(true);
    try {
      const r = await api.handwritingAdd({ from_list: n });
      toast(r.created.length ? `Added ${r.created.map((c) => c.character).join(" ")} to Writing` : "The list is complete");
      void load();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section class="card">
      <h2>Handwriting</h2>
      {total === 0 ? (
        <p class="muted small">The HSK handwriting list isn't imported yet. Run ops/import-data.sh.</p>
      ) : (
        <>
          <p class="muted small">
            Official HSK 3.0 handwriting list, written from memory and scheduled like any card.
            Practise in Review → Writing.
          </p>
          <ul class="levels">
            {hw.bands.map((b) => (
              <li key={b.band} class="level">
                <span class="level-name">{b.band}</span>
                <span class="meter" role="meter" aria-valuemin={0} aria-valuemax={b.total} aria-valuenow={b.written}
                  aria-label={`HSK ${b.band} handwriting`}>
                  <span style={{ width: `${b.total ? (b.written / b.total) * 100 : 0}%` }} />
                  <span class="meter-ghost" style={{ width: `${b.total ? (b.practising / b.total) * 100 : 0}%` }} />
                </span>
                <span class="level-num">{b.written} / {b.total}</span>
                <span class="level-pct muted">{b.practising}</span>
              </li>
            ))}
          </ul>
          <p class="muted small legend">Solid: written reliably. Light: practising. Last column: in practice.</p>
          <div class="row wrap">
            <button class="btn primary" disabled={busy} onClick={() => add(5)}>Add the next 5</button>
            <button class="btn" disabled={busy} onClick={() => add(10)}>Next 10</button>
          </div>
          {hw.own_characters > 0 && <p class="muted small">Plus {hw.own_characters} characters you added yourself.</p>}
        </>
      )}
    </section>
  );
}
