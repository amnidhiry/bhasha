import { useEffect, useState } from "preact/hooks";

// Hash routes keep the service worker and the API's SPA fallback simple:
//   #/            library      #/read/12   reader
//   #/review      reviews      #/progress  progress
export type Route =
  | { name: "library" }
  | { name: "read"; id: number }
  | { name: "review" }
  | { name: "progress" };

export function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/");
  if (parts[0] === "read" && parts[1]) return { name: "read", id: Number(parts[1]) };
  if (parts[0] === "review") return { name: "review" };
  if (parts[0] === "progress") return { name: "progress" };
  return { name: "library" };
}

export const go = (path: string) => (location.hash = path);

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(location.hash));
  useEffect(() => {
    const on = () => setRoute(parse(location.hash));
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  return route;
}
