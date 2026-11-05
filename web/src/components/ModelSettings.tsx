import { useEffect, useState } from "preact/hooks";
import { api, type LlmStatus } from "../api";
import { toast } from "./Toast";

/** Sign in with ChatGPT (plan usage, no API key), or connect LM Studio / an API key. */
export function ModelSettings() {
  const [st, setSt] = useState<LlmStatus | null>(null);
  const [models, setModels] = useState<{ id: string; name: string }[]>([]);
  const [flow, setFlow] = useState<{ flow_id: string; authorize_url: string } | null>(null);
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [compat, setCompat] = useState({ url: "", key: "", model: "" });

  const refresh = async () => {
    const s = await api.llmStatus().catch(() => null);
    setSt(s);
    if (s?.connected) api.llmModels().then(setModels).catch(() => setModels([]));
  };
  useEffect(() => void refresh(), []);

  async function run<T>(fn: () => Promise<T>, ok?: string) {
    setBusy(true);
    try {
      const r = await fn();
      if (ok) toast(ok);
      return r;
    } catch (e) {
      toast((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function startSignIn() {
    const f = await run(() => api.chatgptStart());
    if (!f) return;
    setFlow(f);
    window.open(f.authorize_url, "_blank", "noopener");
  }

  async function finish() {
    if (!flow) return;
    const s = await run(() => api.chatgptFinish(flow.flow_id, address), "Signed in with ChatGPT");
    if (s) {
      setFlow(null);
      setAddress("");
      void refresh();
    }
  }

  if (!st) return null;
  return (
    <section class="card">
      <h2>Text generation</h2>
      {!st.secret_key_set && (
        <p class="error small">Set BHASHA_SECRET_KEY in the server's .env first (openssl rand -hex 32); sign-ins are stored encrypted with it.</p>
      )}

      {st.connected ? (
        <>
          <p class="muted small">
            {st.kind === "chatgpt" ? <>ChatGPT plan{st.email ? <> · {st.email}</> : null}</> : <>{st.base_url}</>}
            {" · "}{st.calls_today}/{st.daily_cap} calls today
          </p>
          <label class="field">
            <span>Model</span>
            <select value={st.model ?? ""} disabled={busy}
              onChange={(e) => run(() => api.setModel(e.currentTarget.value), "Model set").then((s) => s && setSt(s))}>
              {!st.model && <option value="">Choose…</option>}
              {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              {st.model && !models.some((m) => m.id === st.model) && <option value={st.model}>{st.model}</option>}
            </select>
          </label>
          <button class="btn quiet" disabled={busy} onClick={() => run(() => api.signOut(), "Signed out").then(() => refresh())}>
            {st.kind === "chatgpt" ? "Sign out of ChatGPT" : "Disconnect"}
          </button>
        </>
      ) : flow ? (
        <>
        <ol class="steps">
          <li>
            Approve bhasha in the tab that opened.{" "}
            <a href={flow.authorize_url} target="_blank" rel="noopener">Open it again</a>
          </li>
          <li>The tab then shows a page that can't load, at an address starting with <code>http://127.0.0.1</code>. That's expected.</li>
          <li>
            Copy that whole address and paste it here:
            <div class="row-input">
              <input value={address} onInput={(e) => setAddress(e.currentTarget.value)} placeholder="http://127.0.0.1:1455/callback?code=…"
                autocomplete="off" autocapitalize="off" spellcheck={false} />
              <button class="btn primary" disabled={busy || !address.includes("code=")} onClick={finish}>Finish</button>
            </div>
          </li>
        </ol>
        <button class="btn quiet" onClick={() => setFlow(null)}>Cancel</button>
        </>
      ) : (
        <>
          <p class="muted small">
            Generated stories use your ChatGPT Plus or Pro plan. No API key, no extra cost; it counts toward your plan's usage.
          </p>
          <button class="btn primary" disabled={busy || !st.secret_key_set} onClick={startSignIn}>Sign in with ChatGPT</button>
          <details class="sub">
            <summary>Use LM Studio or an API key instead</summary>
            <div class="form compact">
              <label><span>Base URL</span><input value={compat.url} placeholder="http://lmstudio.lan:1234/v1"
                onInput={(e) => setCompat({ ...compat, url: e.currentTarget.value })} /></label>
              <label><span>API key (optional)</span><input type="password" value={compat.key}
                onInput={(e) => setCompat({ ...compat, key: e.currentTarget.value })} /></label>
              <label><span>Model (optional)</span><input value={compat.model}
                onInput={(e) => setCompat({ ...compat, model: e.currentTarget.value })} /></label>
              <button class="btn" disabled={busy || !compat.url}
                onClick={() => run(() => api.connectCompatible(compat.url, compat.key || null, compat.model || null), "Connected").then(() => refresh())}>
                Connect
              </button>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
