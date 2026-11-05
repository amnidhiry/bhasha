import HanziWriter from "hanzi-writer";
import { useEffect, useImperativeHandle, useRef } from "preact/hooks";
import { forwardRef } from "preact/compat";
import { getSettings, setSettings, useSettings } from "../settings";
import { toast } from "./Toast";

export interface PadHandle {
  hint: () => void;
  giveUp: () => void;
}

interface Props {
  char: string;
  onDone: (mistakes: number) => void;
}

type Loader = NonNullable<Parameters<typeof HanziWriter.create>[2]>["charDataLoader"];
export const loadChar: NonNullable<Loader> = (ch, onLoad, onError) => {
  fetch(`/api/hanzi/${encodeURIComponent(ch)}`)
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(onLoad, onError);
};

const cssColor = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#333";

/**
 * Hanzi Writer quiz with Apple Pencil palm rejection.
 *
 * Hanzi Writer listens to touch and mouse events. On iPad a Pencil arrives as
 * touches with touchType "stylus". In Pencil-only mode every touch is stopped
 * before Hanzi Writer sees it, and stylus touches are replayed as mouse events,
 * so a resting palm can't draw a stroke.
 */
export const WritingPad = forwardRef<PadHandle, Props>(function WritingPad({ char, onDone }, ref) {
  const host = useRef<HTMLDivElement>(null);
  const writer = useRef<HanziWriter | null>(null);
  const done = useRef(false);
  const { pencilOnly } = useSettings();

  useEffect(() => {
    const el = host.current!;
    el.innerHTML = "";
    done.current = false;
    const size = Math.min(420, el.clientWidth || 300);
    const w = HanziWriter.create(el, char, {
      width: size,
      height: size,
      padding: 18,
      showCharacter: false,
      showOutline: false,
      highlightOnComplete: true,
      leniency: 1,
      showHintAfterMisses: 3,
      drawingWidth: 22,
      strokeColor: cssColor("--ink"),
      outlineColor: cssColor("--rule"),
      drawingColor: cssColor("--ink"),
      highlightColor: cssColor("--accent"),
      charDataLoader: loadChar,
      onLoadCharDataError: () => toast(`No stroke data for ${char}`),
    });
    writer.current = w;
    void w.quiz({
      onComplete: ({ totalMistakes }) => {
        if (done.current) return;
        done.current = true;
        onDone(totalMistakes);
      },
    });
    return () => {
      writer.current = null;
      el.innerHTML = "";
    };
  }, [char]);

  // Palm rejection: capture-phase handlers on the host run before Hanzi Writer's.
  useEffect(() => {
    const el = host.current!;
    const svg = () => el.querySelector("svg");
    const replay = (type: "mousedown" | "mousemove" | "mouseup", t: Touch) => {
      const target = type === "mouseup" ? document : svg();
      target?.dispatchEvent(new MouseEvent(type, { clientX: t.clientX, clientY: t.clientY, bubbles: true }));
    };
    // Safari (iPad) marks Pencil touches with touchType "stylus". Other browsers lack
    // touchType; there a pen pointer being down marks the touches as the pen's.
    let penDown = false;
    const onPointer = (e: PointerEvent) => {
      if (e.pointerType === "pen") penDown = e.type === "pointerdown" || (penDown && e.type !== "pointerup" && e.type !== "pointercancel");
    };
    const isStylus = (t: Touch) => {
      const type = (t as Touch & { touchType?: string }).touchType;
      return type ? type === "stylus" : penDown;
    };
    const handle = (type: "mousedown" | "mousemove" | "mouseup") => (e: TouchEvent) => {
      const stylus = [...e.changedTouches].find(isStylus);
      if (stylus && !getSettings().pencilOnly) {
        setSettings({ pencilOnly: true });
        toast("Apple Pencil detected: finger touches are now ignored on the writing pad.");
      }
      if (!getSettings().pencilOnly) return; // fingers allowed: Hanzi Writer handles touches itself
      e.preventDefault();
      e.stopPropagation();
      if (stylus) replay(type, stylus);
    };
    const start = handle("mousedown"), move = handle("mousemove"), end = handle("mouseup");
    for (const t of ["pointerdown", "pointerup", "pointercancel"] as const) el.addEventListener(t, onPointer, { capture: true });
    el.addEventListener("touchstart", start, { capture: true, passive: false });
    el.addEventListener("touchmove", move, { capture: true, passive: false });
    el.addEventListener("touchend", end, { capture: true, passive: false });
    return () => {
      el.removeEventListener("touchstart", start, { capture: true });
      el.removeEventListener("touchmove", move, { capture: true });
      el.removeEventListener("touchend", end, { capture: true });
      for (const t of ["pointerdown", "pointerup", "pointercancel"] as const) el.removeEventListener(t, onPointer, { capture: true });
    };
  }, []);

  useImperativeHandle(ref, () => ({
    hint: () => void writer.current?.showOutline(),
    giveUp: () => {
      const w = writer.current;
      if (!w) return;
      done.current = true;
      void w.cancelQuiz();
      void w.showCharacter();
      void w.animateCharacter();
    },
  }));

  return (
    <div class="pad-wrap">
      <div class="pad tianzige" ref={host} aria-label={`Writing pad for the character`} />
      <label class="pencil-toggle">
        <input type="checkbox" checked={pencilOnly} onChange={(e) => setSettings({ pencilOnly: e.currentTarget.checked })} />
        <span>Pencil only (ignore fingers)</span>
      </label>
    </div>
  );
});
