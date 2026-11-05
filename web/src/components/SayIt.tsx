import { useState } from "preact/hooks";
import { classify, contour, target, track, type Guess } from "../pitch";

const SECONDS = 1.6;

/** Record one syllable and draw its pitch against the target tone's shape. */
export function SayIt({ tone, chao, label }: { tone: number; chao: number[]; label: string }) {
  const [state, setState] = useState<"idle" | "recording" | "done" | "error">("idle");
  const [mine, setMine] = useState<number[]>([]);
  const [guess, setGuess] = useState<Guess | null>(null);
  const [error, setError] = useState("");

  async function record() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setState("error");
      setError("The microphone needs HTTPS (open bhasha through Traefik).");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false } });
      const rec = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => chunks.push(e.data);
      const stopped = new Promise((r) => (rec.onstop = r));
      setState("recording");
      rec.start();
      await new Promise((r) => setTimeout(r, SECONDS * 1000));
      rec.stop();
      await stopped;
      stream.getTracks().forEach((t) => t.stop());
      const ctx = new AudioContext();
      const buf = await ctx.decodeAudioData(await new Blob(chunks, { type: rec.mimeType }).arrayBuffer());
      void ctx.close();
      const c = contour(track(buf.getChannelData(0), buf.sampleRate));
      setMine(c);
      setGuess(classify(c));
      setState("done");
    } catch (e) {
      setState("error");
      setError((e as Error).name === "NotAllowedError" ? "Microphone permission was denied." : `Recording failed: ${(e as Error).message}`);
    }
  }

  const goal = target(chao);
  const W = 260, H = 110, Y = 9; // y range ±9 semitones
  const path = (pts: number[]) =>
    pts.map((v, i) => `${i ? "L" : "M"}${((i / Math.max(1, pts.length - 1)) * W).toFixed(1)},${(H / 2 - (Math.max(-Y, Math.min(Y, v)) / Y) * (H / 2 - 6)).toFixed(1)}`).join(" ");

  return (
    <div class="sayit">
      <button class={`btn ${state === "recording" ? "recording" : ""}`} onClick={record} disabled={state === "recording"}>
        {state === "recording" ? "Listening…" : state === "done" ? "Say it again" : `Say ${label}`}
      </button>
      {(state === "done" || state === "recording") && (
        <svg class="contour" viewBox={`0 0 ${W} ${H}`} role="img"
          aria-label={`Your pitch compared with tone ${tone}${guess?.tone ? `; it sounds like tone ${guess.tone}` : ""}`}>
          <line x1="0" x2={W} y1={H / 2} y2={H / 2} class="mid" />
          <path d={path(goal)} class="goal" />
          {mine.length > 0 && <path d={path(mine)} class="mine" />}
        </svg>
      )}
      {state === "done" && guess && (
        <p class={`small ${guess.tone === tone ? "ok" : "muted"}`}>
          {guess.tone ? `Sounds like tone ${guess.tone}. ${guess.reason}` : guess.reason}
          {guess.tone && guess.tone !== tone ? " The dashed line is the target." : ""}
        </p>
      )}
      {state === "error" && <p class="error small">{error}</p>}
    </div>
  );
}
