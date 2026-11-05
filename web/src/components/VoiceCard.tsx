import { useEffect, useState } from "preact/hooks";
import { api, type SpeechStatus } from "../api";
import { pct } from "../format";
import { speak } from "../speech";
import { PlayIcon } from "./LookupSheet";
import { toast } from "./Toast";

/** Speech hosts, the chosen voice, and how well each voice gets Mandarin tones right. */
export function VoiceCard() {
  const [st, setSt] = useState<SpeechStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.speech().then(setSt).catch(() => setSt(null));
  useEffect(() => void load(), []);
  if (!st) return null;

  const checks = st.tone_check;
  const score = (v: string) => (checks[v]?.accuracy != null ? ` · tones ${pct(checks[v].accuracy)}` : "");
  const current = st.voice ? checks[st.voice] : undefined;

  async function check() {
    setBusy(true);
    try {
      await api.toneCheck(st!.voices.slice(0, 8));
      toast("Checking tones in the background; it takes a minute or two per voice.");
      setTimeout(load, 60_000);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section class="card">
      <h2>Voice</h2>
      {st.hosts.length === 0 ? (
        <p class="muted small">Using your device's Mandarin voice. Set BHASHA_SPEECH_URLS to use the speech service.</p>
      ) : (
        <ul class="hosts">
          {st.hosts.map((h) => (
            <li key={h.url}>
              <span class={`dot ${h.online ? "on" : ""}`} aria-hidden="true" />
              <span class="small">{h.url}</span>
              <span class="muted small">{h.online ? `${h.engine} on ${h.device}` : "offline"}{st.active === h.url ? " · in use" : ""}</span>
            </li>
          ))}
        </ul>
      )}
      {st.hosts.length > 0 && !st.active && <p class="muted small">No host answering: the device voice is used until one is back.</p>}

      {st.voices.length > 0 && (
        <>
          <label class="field">
            <span>Voice</span>
            <select value={st.voice ?? ""} disabled={busy}
              onChange={(e) => api.speechVoice(e.currentTarget.value).then(setSt).catch((err) => toast(err.message))}>
              {st.voices.map((v) => <option key={v} value={v}>{v}{score(v)}</option>)}
            </select>
          </label>
          <div class="row wrap">
            <button class="btn" onClick={() => speak("你好，我们一起学习中文吧。")}><PlayIcon /> Sample</button>
            <button class="btn" disabled={busy} onClick={check}>Check tones</button>
          </div>
          {current?.accuracy != null ? (
            <p class="small">
              {st.voice}: tones right on {current.n} test syllables {pct(current.accuracy)}
              {" "}(1: {pct(current.per_tone["1"])}, 2: {pct(current.per_tone["2"])}, 3: {pct(current.per_tone["3"])}, 4: {pct(current.per_tone["4"])}).
              {current.accuracy < 0.85 && " Below 85%: try another voice before relying on it for tones."}
            </p>
          ) : (
            <p class="muted small">Not tone-checked yet. A voice that gets tones wrong teaches wrong tones, so check before relying on it.</p>
          )}
          {current && current.misses.length > 0 && (
            <p class="muted small" lang="zh-CN">
              Misheard:{" "}
              {current.misses.map((m) => (
                <button key={m.key} class="link-btn inline" onClick={() => speak(m.char)}>
                  {m.char} ({m.tone}→{m.heard ?? "?"})
                </button>
              ))}
            </p>
          )}
        </>
      )}
    </section>
  );
}
