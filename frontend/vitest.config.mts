import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // CopilotKit's v2 entry imports its own stylesheet, which Node cannot load; inlined, Vite
    // handles the CSS import like any other.
    server: { deps: { inline: [/@copilotkit\//] } },
  },
});
