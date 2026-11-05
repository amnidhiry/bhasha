import { defineConfig } from "vite";

// Dev: `npm run dev` proxies /api to the backend on :8000.
export default defineConfig({
  oxc: { jsx: { runtime: "automatic", importSource: "preact" } },
  server: { proxy: { "/api": "http://localhost:8000", "/health": "http://localhost:8000" } },
  build: { outDir: "dist", assetsDir: "assets" },
});
