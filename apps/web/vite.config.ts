import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API is proxied in development so the browser sees a same-origin app and
// CORS never enters the picture. In production the app is served behind the
// same host, or VITE_API_BASE_URL points at the API.
export default defineConfig({
  plugins: [react()],
  // Mirrors the `paths` mapping in tsconfig.json; both must agree.
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      "/v1": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
