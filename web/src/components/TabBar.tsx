import { has, lang, tl } from "../lang";
import type { Route } from "../router";

const tabs = [
  { name: "library", href: "#/", label: "Read" },
  { name: "review", href: "#/review", label: "Review" },
  { name: "journal", href: "#/journal", label: "Write" },
  { name: "sounds", href: "#/sounds", label: "Sounds", feature: "bootcamp" },
  { name: "progress", href: "#/progress", label: "Progress" },
] as const;

export function TabBar({ route, due }: { route: Route; due: number }) {
  const active = route.name === "read" ? "library" : route.name === "drill" ? "sounds" : route.name === "talk" ? "journal" : route.name === "char" || route.name === "chars" ? "progress" : route.name;
  return (
    <nav class="tabbar" aria-label="Main">
      {tabs.filter((t) => !("feature" in t) || has(t.feature)).map((t) => (
        <a key={t.name} href={t.href} class={active === t.name ? "active" : ""} aria-current={active === t.name ? "page" : undefined}>
          <span class="tab-glyph" aria-hidden="true" lang={tl()}>{lang().glyphs[t.name] ?? t.label[0]}</span>
          <span class="tab-label">{t.label}</span>
          {t.name === "review" && due > 0 && <span class="badge" aria-label={`${due} due`}>{due > 99 ? "99+" : due}</span>}
        </a>
      ))}
    </nav>
  );
}
