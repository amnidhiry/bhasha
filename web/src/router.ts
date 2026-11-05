import { useEffect, useState } from "preact/hooks";

// Hash routes keep the service worker and the API's SPA fallback simple:
//   #/            library      #/read/12   reader
//   #/review      reviews      #/progress  progress
//   #/sounds      bootcamp     #/sounds/drill/tone  a drill
export type Route =
  | { name: "library" }
  | { name: "read"; id: number }
  | { name: "review" }
  | { name: "progress" }
  | { name: "sounds" }
  | { name: "journal" }
  | { name: "talk"; id?: number }
  | { name: "drill"; drill: string }
  | { name: "char"; char: string } // #/char/银  character page
  | { name: "chars"; component?: string }; // #/chars  overview, #/chars/氵  component explorer

export function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/");
  if (parts[0] === "read" && parts[1]) return { name: "read", id: Number(parts[1]) };
  if (parts[0] === "review") return { name: "review" };
  if (parts[0] === "progress") return { name: "progress" };
  if (parts[0] === "sounds" && parts[1] === "drill" && parts[2]) return { name: "drill", drill: decodeURIComponent(parts[2]) };
  if (parts[0] === "sounds") return { name: "sounds" };
  if (parts[0] === "journal") return { name: "journal" };
  if (parts[0] === "talk") return parts[1] ? { name: "talk", id: Number(parts[1]) } : { name: "talk" };
  if (parts[0] === "char" && parts[1]) return { name: "char", char: decodeURIComponent(parts[1]) };
  if (parts[0] === "chars") return { name: "chars", component: parts[1] ? decodeURIComponent(parts[1]) : undefined };
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
