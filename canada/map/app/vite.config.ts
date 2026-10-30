import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";

// The design tokens live in canada/design/ (Agent 06's lane) and are imported
// directly, so the dev server must be allowed to read that folder.
const designDir = fileURLToPath(new URL("../../design", import.meta.url));
const appDir = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "./",
  server: { fs: { allow: [appDir, designDir] } },
  build: { chunkSizeWarningLimit: 1500 },
});
