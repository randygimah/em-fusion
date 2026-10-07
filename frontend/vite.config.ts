import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { apiProxyTarget } from "./devProxy";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
  server: {
    port: 1234,
    open: true,
    hmr: true,
    proxy: {
      // The backend serves the /api/v1 prefix itself, so the path passes
      // through unrewritten — matching what nginx does in the container.
      // The address is localhost:8000 on the host and the backend service
      // inside the `frontend-dev` container (ops-006).
      "/api": {
        target: apiProxyTarget(process.env),
        changeOrigin: true,
      },
    },
  },
});
