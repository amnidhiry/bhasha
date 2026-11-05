// Interim audio via the browser's built-in Mandarin voice (iOS and macOS ship
// one). Replaced by server-rendered CosyVoice audio in the speech phase.

let voice: SpeechSynthesisVoice | null | undefined;

function pickVoice(): SpeechSynthesisVoice | null {
  const voices = speechSynthesis.getVoices();
  return (
    voices.find((v) => v.lang === "zh-CN" && /premium|enhanced/i.test(v.name)) ??
    voices.find((v) => v.lang === "zh-CN") ??
    voices.find((v) => v.lang.startsWith("zh")) ??
    null
  );
}

export const canSpeak = () => typeof window !== "undefined" && "speechSynthesis" in window;

export function speak(text: string, rate = 0.85) {
  if (!canSpeak()) return;
  if (voice === undefined || voice === null) voice = pickVoice();
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "zh-CN";
  u.rate = rate;
  if (voice) u.voice = voice;
  speechSynthesis.speak(u);
}

if (canSpeak()) speechSynthesis.addEventListener?.("voiceschanged", () => (voice = pickVoice()));
