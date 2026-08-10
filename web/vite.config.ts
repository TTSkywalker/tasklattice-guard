import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  plugins: [tailwindcss(), react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8091",
      "/health": "http://127.0.0.1:8091",
    },
  },
});
