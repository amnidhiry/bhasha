import { useEffect, useState } from "preact/hooks";
import { api, type FsrsStatus } from "../api";
import { saveParams } from "../outbox";
import { pct } from "../format";
import { toast } from "./Toast";

const RETENTIONS = [0.8, 0.85, 0.9, 0.95];

/** FSRS fitted to your own reviews: progress toward the first fit, history, retention. */
export function SchedulingCard() {
  const [st, setSt] = useState<FsrsStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.fsrs().then(setSt).catch(() => setSt(null));
  useEffect(() => void load(), []);
  if (!st) return null;

  async function act(fn: () => Promise<FsrsStatus>, ok: string) {
    setBusy(true);
    try {
      setSt(await fn());
      // Keep the offline scheduler in step with the server's.
      api.schedulerParams().then(saveParams).catch(() => {});
      toast(ok);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const last = st.history.find((h) => h.status !== "skipped") ?? st.history[0];
  const before = last?.metrics.holdout_current, after = last?.metrics.holdout_fitted;
  return (
    <section class="card">
      <h2>Scheduling</h2>
      {st.personalized ? (
        <p class="small">
          <b class="ok">Fitted to you</b> from {st.history.find((h) => h.status === "accepted")?.n_reviews.toLocaleString()} reviews.
          It re-fits monthly, or sooner as your log grows.
        </p>
      ) : (
        <>
          <p class="small muted">
            Reviews are scheduled with FSRS's default model. After {st.min_reviews} reviews it's fitted to how your memory
            actually behaves, and the new fit is used only if it predicts unseen reviews better.
          </p>
          <span class="meter" role="meter" aria-valuemin={0} aria-valuemax={st.min_reviews} aria-valuenow={st.reviews}
            aria-label="Reviews toward the first fit">
            <span style={{ width: `${Math.min(100, (st.reviews / st.min_reviews) * 100)}%` }} />
          </span>
          <p class="muted small">{st.reviews.toLocaleString()} / {st.min_reviews} reviews</p>
        </>
      )}

      {last && last.status !== "skipped" && before?.log_loss != null && after?.log_loss != null && (
        <p class="muted small">
          Last fit ({new Date(last.created_at).toLocaleDateString()}): {last.status}. On {after.n} held-out reviews, log loss{" "}
          {before.log_loss.toFixed(3)} → {after.log_loss.toFixed(3)}, calibration error {pct(before.rmse_bins)} → {pct(after.rmse_bins)}.
        </p>
      )}
      {last && last.status === "skipped" && <p class="muted small">Last check: {last.message}</p>}

      <div class="row wrap">
        <button class="btn" disabled={busy || st.fit_running || st.reviews < st.min_reviews}
          onClick={() => act(() => api.fsrsFit(), "Fit queued; it runs in the background")}>
          {st.fit_running ? "Fitting…" : "Fit now"}
        </button>
      </div>

      <h3 class="sub-h">Target recall</h3>
      <p class="muted small">
        How likely you should be to remember a card when it comes up. Higher means more reviews.
      </p>
      <div class="seg" role="radiogroup" aria-label="Target recall">
        {RETENTIONS.map((r) => (
          <button key={r} role="radio" aria-checked={Math.abs(st.desired_retention - r) < 1e-6}
            class={Math.abs(st.desired_retention - r) < 1e-6 ? "on" : ""} disabled={busy}
            onClick={() => act(() => api.fsrsRetention(r === 0.9 ? null : r), `Target recall ${pct(r)}`)}>
            {pct(r)}
          </button>
        ))}
      </div>
      {st.suggested_retention != null && Math.abs(st.suggested_retention - st.desired_retention) > 1e-6 && (
        <p class="small">
          Your reviews suggest {pct(st.suggested_retention)}: the least total study time for what you retain.{" "}
          <button class="link-btn" disabled={busy}
            onClick={() => act(() => api.fsrsRetention(st.suggested_retention), `Target recall ${pct(st.suggested_retention)}`)}>
            Use it
          </button>
        </p>
      )}
    </section>
  );
}
