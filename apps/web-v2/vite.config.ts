import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// The Vue 3 SPA is served from the existing Python server at `/v2/` (see
// `server_app/core.py` end-of-file T-036 static handler). Setting `base` makes
// all built asset URLs resolve against that prefix in production while keeping
// dev (`npm run dev`) on Vite's own root.
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/v2/" : "/",
  plugins: [vue()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5174,
    strictPort: false,
  },
}));
