import { speak } from "./speech";

export interface AudioSpec {
  key: string;
  char: string | null;
  text: string | null;
  speakers: string[];
}

let current: HTMLAudioElement | null = null;

/** Recorded Tone Perfect audio when imported (a random one of six voices, for
 * talker variety), else the device's Mandarin voice reading the character. */
export function play(a: AudioSpec, rate = 0.75) {
  current?.pause();
  if (a.speakers.length) {
    const speaker = a.speakers[Math.floor(Math.random() * a.speakers.length)];
    current = new Audio(`/api/audio/${encodeURIComponent(a.key)}?speaker=${speaker}`);
    void current.play().catch(() => speak(a.text ?? a.char ?? "", rate));
    return;
  }
  speak(a.text ?? a.char ?? "", rate);
}
