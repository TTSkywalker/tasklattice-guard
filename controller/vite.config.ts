import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

const controllerDevProxy = process.env.CONTROLLER_DEV_PROXY ?? "http://127.0.0.1:8080";

export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  plugins: [tailwindcss(), react()],
  server: {
    proxy: {
      "/api": controllerDevProxy,
      "/health": controllerDevProxy,
    },
  },
});
