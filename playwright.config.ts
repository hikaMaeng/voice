import { defineConfig } from "@playwright/test";

// 배포된 서버(npm run deploy)를 대상으로 한다 — 서버를 띄우지 않는다
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 15 * 60_000,
  expect: { timeout: 30_000 },
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "tests/e2e/.artifacts/results.json" }]],
  outputDir: "tests/e2e/.artifacts/out",
  use: {
    baseURL: process.env.VOICE_E2E_BASE || "http://127.0.0.1:8765",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    locale: "ko-KR",
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
  },
});
