import { defineConfig } from "vite";

// `npm run dev` expects `book-links serve` on port 8765 for the graph and the review API.
export default defineConfig({
  base: "./",
  server: {
    proxy: {
      "/graph.json": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
});
