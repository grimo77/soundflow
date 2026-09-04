import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:7777",
      "/ws": { target: "ws://localhost:7777", ws: true },
      "/cloudws": "http://localhost:7777",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
