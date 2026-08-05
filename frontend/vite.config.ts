import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    coverage: {
      all: true,
      exclude: [
        "**/*.d.ts",
        "**/*.test.{ts,tsx,mjs}",
        "src/**/*.test.helpers.{ts,tsx}",
        "src/**/*.testSupport.{ts,tsx}",
        "src/**/*TestSupport.{ts,tsx}",
        "src/testing/**",
        "coverage/**",
        "dist/**",
        "node_modules/**",
      ],
      include: ["src/**/*.{ts,tsx}", "electron/**/*.mjs"],
      provider: "v8",
      reporter: ["text", "json-summary", "lcov"],
      reportsDirectory: "coverage",
    },
  },
  build: {
    chunkSizeWarningLimit: 550,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/hls.js")) {
            return "hls";
          }
          if (
            id.includes("node_modules/react/") ||
            id.includes("node_modules/react-dom/")
          ) {
            return "vendor";
          }
          return undefined;
        },
      },
    },
  },
});
