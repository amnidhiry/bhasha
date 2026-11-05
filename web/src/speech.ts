// Speech: the homelab's speech service first (cached server-side, any voice you
// chose after the tone check), the device's own voice for the language as the fallback.
// After a server failure the device voice is used for a minute, so an offline
// speech host never adds a delay to every tap.

import { tl } from "./lang";

let voice: SpeechSynthesisVoice | null | undefined;
let serverDownUntil = 0;
let current: HTMLAudioElement | null = null;

function pickVoice(): SpeechSynthesisVoice | null {
  const voices = speechSynthesis.getVoices();
  const want = tl(); // "zh-CN", "bn-IN"
  const base = want.split("-")[0];
  const same = (v: SpeechSynthesisVoice) => v.lang.replace("_", "-") === want;
  return (
    voices.find((v) => same(v) && /premium|enhanced/i.test(v.name)) ??
    voices.find(same) ??
    voices.find((v) => v.lang.startsWith(base)) ??
    null
  );
}

export const canSpeak = () => typeof window !== "undefined" && ("speechSynthesis" in window || "Audio" in window);

function deviceSpeak(text: string, rate: number, onEnd?: () => void) {
  if (!("speechSynthesis" in window)) return onEnd?.();
  if (voice === undefined || voice === null) voice = pickVoice();
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = tl();
  u.rate = rate;
  if (voice) u.voice = voice;
  if (onEnd) u.onend = () => onEnd();
  speechSynthesis.speak(u);
}

/** Speak `text`. `rate` 0.85 is the learner-friendly default. */
export function speak(text: string, rate = 0.85, onEnd?: () => void) {
  if (!text) return;
  current?.pause();
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  if (Date.now() < serverDownUntil) return deviceSpeak(text, rate, onEnd);
  const audio = new Audio(`/api/tts?text=${encodeURIComponent(text)}&speed=${rate.toFixed(2)}`);
  current = audio;
  let fellBack = false;
  const fallback = () => {
    if (fellBack || current !== audio) return;
    fellBack = true;
    serverDownUntil = Date.now() + 60_000;
    deviceSpeak(text, rate, onEnd);
  };
  audio.onerror = fallback;
  if (onEnd) audio.onended = () => onEnd();
  audio.play().catch(fallback);
}

/** Speak sentences one after another (the service takes one sentence at a time). */
export function speakAll(sentences: string[], rate = 0.85) {
  const queue = sentences.filter((s) => s.trim());
  const next = () => {
    const s = queue.shift();
    if (s) speak(s, rate, next);
  };
  next();
}

export function stopSpeaking() {
  current?.pause();
  if ("speechSynthesis" in window) speechSynthesis.cancel();
}

if (typeof window !== "undefined" && "speechSynthesis" in window) {
  speechSynthesis.addEventListener?.("voiceschanged", () => (voice = pickVoice()));
}
