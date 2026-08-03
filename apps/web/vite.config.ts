import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API is proxied so the browser sees a same-origin app and CORS never
// enters the picture. In production the app is served behind the same host, or
// VITE_API_BASE_URL points at the API.
const API_PROXY = {
  "/v1": { target: "http://127.0.0.1:8000", changeOrigin: true },
  "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
};

export default defineConfig({
  plugins: [react()],
  // Mirrors the `paths` mapping in tsconfig.json; both must agree.
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: API_PROXY,
  },
  // `preview` serves the production build. The end-to-end suite runs against
  // it rather than the dev server: no on-demand transform, and it exercises
  // the artefact that actually ships.
  preview: {
    port: 4173,
    proxy: API_PROXY,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
