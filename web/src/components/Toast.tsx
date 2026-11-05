import { useEffect, useState } from "preact/hooks";

let push: ((msg: string) => void) | null = null;
export const toast = (msg: string) => push?.(msg);

export function ToastHost() {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    let t: number | undefined;
    push = (m) => {
      setMsg(m);
      clearTimeout(t);
      t = window.setTimeout(() => setMsg(null), 2600);
    };
    return () => {
      push = null;
    };
  }, []);
  return msg ? <div class="toast" role="status">{msg}</div> : null;
}
