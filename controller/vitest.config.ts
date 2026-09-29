import { mergeConfig, defineConfig } from "vitest/config";
import viteConfig from "./vite.config";
export default mergeConfig(
  viteConfig,
  defineConfig({ test: { setupFiles: ["./src/test/browser-apis.ts"] } }),
);
