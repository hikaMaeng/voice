import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 빌드 결과(web/dist)는 voice 서버가 `/` 에서 서빙한다(app.py: /assets 마운트 + index.html 폴백).
export default defineConfig({
  base: "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  preview: {
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
