import type { Route } from "../router";

const tabs = [
  { name: "library", href: "#/", label: "Read", glyph: "读" },
  { name: "review", href: "#/review", label: "Review", glyph: "复" },
  { name: "sounds", href: "#/sounds", label: "Sounds", glyph: "音" },
  { name: "progress", href: "#/progress", label: "Progress", glyph: "进" },
] as const;

export function TabBar({ route, due }: { route: Route; due: number }) {
  const active = route.name === "read" ? "library" : route.name === "drill" ? "sounds" : route.name;
  return (
    <nav class="tabbar" aria-label="Main">
      {tabs.map((t) => (
        <a key={t.name} href={t.href} class={active === t.name ? "active" : ""} aria-current={active === t.name ? "page" : undefined}>
          <span class="tab-glyph" aria-hidden="true">{t.glyph}</span>
          <span class="tab-label">{t.label}</span>
          {t.name === "review" && due > 0 && <span class="badge" aria-label={`${due} due`}>{due > 99 ? "99+" : due}</span>}
        </a>
      ))}
    </nav>
  );
}
