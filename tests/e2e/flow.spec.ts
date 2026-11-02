// 요구사항 1~5 + 「자원 제한은 웹 설정으로」를 화면으로 확인한다. 선택자 계약: docs/ui-contract.md
import { expect, test, type Page } from "@playwright/test";

const API = (p: string) => p;

function sineWav(seconds: number, sr = 16000): Buffer {
  // 말소리 흉내: 3 s 소리 + 1 s 쉼 반복(모의 ASR 이 구간을 나눌 수 있게)
  const n = Math.floor(seconds * sr);
  const data = Buffer.alloc(n * 2);
  for (let i = 0; i < n; i++) {
    const t = i / sr;
    const on = t % 4 < 3 ? 1 : 0;
    data.writeInt16LE(Math.round(on * 0.3 * Math.sin(2 * Math.PI * 200 * t) * 32767), i * 2);
  }
  const h = Buffer.alloc(44);
  h.write("RIFF", 0); h.writeUInt32LE(36 + data.length, 4); h.write("WAVE", 8); h.write("fmt ", 12);
  h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22); h.writeUInt32LE(sr, 24);
  h.writeUInt32LE(sr * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write("data", 36); h.writeUInt32LE(data.length, 40);
  return Buffer.concat([h, data]);
}

async function go(page: Page, name: string) {
  await page.getByTestId("main-nav").getByRole("link", { name }).click();
}

let savedSettings: Record<string, unknown>;
const stamp = Date.now().toString(36);

test.beforeAll(async ({ request }) => {
  savedSettings = await (await request.get(API("/api/settings"))).json();
  await request.put(API("/api/settings"), { data: { show_test_engines: true } });
});

test.afterAll(async ({ request }) => {
  await request.put(API("/api/settings"), { data: { show_test_engines: savedSettings.show_test_engines, allowed_gpus: savedSettings.allowed_gpus } });
});

test("모델 관리: 카탈로그·라이선스 배지·상태", async ({ page }) => {
  await page.goto("/#/models");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  for (const e of ["qwen", "moss", "higgs", "omni", "chat", "cosy", "fish", "drama", "xvoice", "fwhisper", "hfwhisper", "qwen3asr", "sensevoice"]) {
    await expect(page.locator(`[data-testid="engine-section"][data-engine="${e}"]`)).toBeVisible();
  }
  const qwen = page.locator('[data-testid="model-row"][data-model-id="qwen3-tts-1.7b-base"]');
  await expect(qwen.locator("[data-commercial]").first()).toHaveAttribute("data-commercial", "yes");
  await expect(page.locator('[data-testid="model-row"][data-model-id="higgs-v3-4b-tf"] [data-commercial]').first()).toHaveAttribute("data-commercial", "no");
  await expect(page.locator('[data-testid="model-row"][data-model-id="drama-3-q4k"] [data-commercial]').first()).toHaveAttribute("data-commercial", "limited");
  // NAS 에 있는 기본 모델은 확인 ok
  await expect(qwen.getByTestId("model-status")).toHaveAttribute("data-state", "ok", { timeout: 90_000 });
  await expect(qwen.getByRole("button", { name: "위치 지정" })).toBeVisible();
  await expect(page.locator('[data-testid="env-status"][data-env="qwen"]')).toHaveAttribute("data-installed", "true");
});

test("설정: 쓸 GPU 를 웹에서 고른다(하드코딩 아님)", async ({ page, request }) => {
  const sys = await (await request.get(API("/api/system"))).json();
  test.skip(sys.gpus.length === 0, "GPU 없는 기계");
  await page.goto("/#/settings");
  const all = page.getByTestId("settings-all-gpus");
  await expect(page.getByTestId("gpu-row")).toHaveCount(sys.gpus.length);
  if (!(await all.isChecked())) await all.check();
  await page.getByRole("button", { name: "설정 저장" }).click();
  await expect.poll(async () => (await (await request.get(API("/api/settings"))).json()).allowed_gpus).toBeNull();
  // 「전부」를 끄고 첫 카드(가장 큰 메모리 카드)만 남긴다
  const keep = [...sys.gpus].sort((a: any, b: any) => b.total_gb - a.total_gb)[0];
  await all.uncheck();
  for (const g of sys.gpus) {
    const box = page.locator(`[data-testid="gpu-row"][data-gpu-uuid="${g.uuid}"]`).getByTestId("gpu-allow");
    if (g.uuid === keep.uuid) await box.check(); else await box.uncheck();
  }
  await page.getByRole("button", { name: "설정 저장" }).click();
  await expect.poll(async () => (await (await request.get(API("/api/settings"))).json()).allowed_gpus).toEqual([keep.uuid]);
  for (const g of sys.gpus.filter((x: any) => x.uuid !== keep.uuid)) {
    await expect(page.locator(`[data-testid="gpu-row"][data-gpu-uuid="${g.uuid}"]`).getByTestId("gpu-blocked")).toContainText("설정에서 제외");
  }
});

test("참조 세트 → TTS → 결과 불러오기 → ASR → SRT (모의 엔진)", async ({ page, request }) => {
  await page.goto("/#/tts");
  const create = page.getByTestId("ref-create");
  await create.getByTestId("ref-upload-file").setInputFiles({ name: `e2e-${stamp}.wav`, mimeType: "audio/wav", buffer: sineWav(12) });
  await expect(create.getByTestId("ref-upload-status")).toBeVisible();
  await create.getByLabel("세트 이름", { exact: true }).fill(`e2e 세트 ${stamp}`);
  await create.getByRole("radio", { name: /자동/ }).check();
  await create.getByLabel("자동 전사 ASR 모델", { exact: true }).selectOption("mock-asr");
  await expect(create.getByRole("button", { name: "참조 세트 만들기" })).toBeDisabled();   // 동의 전
  await create.getByTestId("ref-consent-basis").selectOption("synthetic");
  await create.getByTestId("ref-consent-agree").check();
  await create.getByRole("button", { name: "참조 세트 만들기" }).click();
  await expect(page.getByTestId("ref-job")).toHaveAttribute("data-status", "done", { timeout: 120_000 });
  const item = page.getByTestId("ref-item").filter({ hasText: `e2e 세트 ${stamp}` });
  await expect(item).toBeVisible();
  // 자동 전사문을 사람이 고친다
  await item.getByText(/전사문·이름 고치기/).click();
  await item.getByTestId("ref-edit-text").fill("사람이 고친 전사문입니다");
  await item.getByRole("button", { name: "세트 저장" }).click();
  await expect(item.getByTestId("ref-text-value")).toContainText("사람이 고친 전사문입니다");
  // 방금 만든 세트는 생성 폼에 자동 선택된다 — 그때 「이 세트로 생성」은 비활성
  const useBtn = item.getByRole("button", { name: "이 세트로 생성" });
  if (await useBtn.isEnabled()) await useBtn.click();
  await expect(item).toHaveAttribute("data-selected", "true");

  const form = page.getByTestId("tts-form");
  await form.getByLabel("TTS 모델", { exact: true }).selectOption("mock-tts");
  await form.getByLabel("대본", { exact: true }).fill("첫 문단 3개입니다.\n\n둘째 문단입니다.");
  await form.getByTestId("param-seed").fill("77");
  await form.getByTestId("param-pitch_hz").fill("330");
  await form.getByRole("button", { name: "생성" }).click();
  await expect(page.getByTestId("tts-job")).toHaveAttribute("data-status", "done", { timeout: 180_000 });
  const result = page.getByTestId("tts-result");
  const genId = await result.getAttribute("data-gen-id");
  expect(genId).toBeTruthy();

  // 결과물: 모든 파라미터와 함께 저장 → 불러오기
  await page.goto(`/#/results/${genId}`);
  const detail = page.getByTestId("gen-detail");
  await expect(detail.getByTestId("gen-seed")).toContainText("77");
  await expect(detail.getByTestId("gen-params")).toContainText("330");
  await expect(detail.getByTestId("gen-parts-table")).toBeVisible();
  await detail.getByRole("button", { name: "불러오기" }).click();
  await expect(page.getByTestId("tts-loaded-banner")).toHaveAttribute("data-ref-mode", "set");
  await expect(page.getByTestId("tts-text")).toHaveValue("첫 문단 3개입니다.\n\n둘째 문단입니다.");
  await expect(page.getByTestId("param-seed")).toHaveValue("77");
  await expect(page.getByTestId("param-pitch_hz")).toHaveValue("330");
  await expect(page.getByTestId("tts-model")).toHaveValue("mock-tts");

  // 불러온 설정으로 다시 생성하면 같은 결과(모의 엔진은 결정적)
  await page.getByTestId("tts-form").getByRole("button", { name: "생성" }).click();
  await expect(page.getByTestId("tts-job")).toHaveAttribute("data-status", "done", { timeout: 180_000 });
  const gen2 = await page.getByTestId("tts-result").getAttribute("data-gen-id");
  const g1 = await (await request.get(API(`/api/generations/${genId}`))).json();
  const g2 = await (await request.get(API(`/api/generations/${gen2}`))).json();
  expect(g2.output.sha256).toBe(g1.output.sha256);
  expect(g2.ref.text).toBe("사람이 고친 전사문입니다");

  // ASR: 같은 업로드를 전사 → 타임라인 → SRT
  await go(page, "ASR");
  const sel = page.getByTestId("asr-upload-select");
  const opt = sel.locator("option", { hasText: `e2e-${stamp}` }).first();
  await sel.selectOption((await opt.getAttribute("value")) as string);
  await page.getByLabel("ASR 모델", { exact: true }).selectOption("mock-asr");
  await page.getByRole("button", { name: "전사 실행" }).click();
  await expect(page.getByTestId("asr-job")).toHaveAttribute("data-status", "done", { timeout: 120_000 });
  const viewer = page.getByTestId("asr-viewer");
  await expect(viewer.getByTestId("asr-segment")).toHaveCount(3);
  await viewer.getByRole("button", { name: /구간 2 재생/ }).click();
  await expect(viewer.getByTestId("asr-current-time")).toHaveAttribute("data-active-index", "1");
  const href = await viewer.getByTestId("asr-export-srt").getAttribute("href");
  const srt = await (await request.get(href as string)).text();
  expect(srt).toContain("00:00:04,000 -->");

  // 작업 화면에 기록이 남는다
  await go(page, "작업");
  await expect(page.locator('[data-testid="job-row"][data-kind="tts"]').first()).toBeVisible();
});

test("실제 엔진: Qwen3-TTS 1.7B 를 웹에서 생성(@gpu)", async ({ page, request }) => {
  test.skip(!process.env.VOICE_E2E_GPU, "VOICE_E2E_GPU=1 일 때만");
  const refs = await (await request.get(API("/api/refs"))).json();
  const ref = refs.find((r: any) => r.mode === "auto" && r.asr && r.asr.model.id === "fw-large-v3");
  test.skip(!ref, "fw-large-v3 로 만든 참조 세트가 필요");
  await page.goto("/#/tts");
  const form = page.getByTestId("tts-form");
  await form.getByLabel("TTS 모델", { exact: true }).selectOption("qwen3-tts-1.7b-base");
  await form.getByLabel("참조 세트", { exact: true }).selectOption(`ref:${ref.id}`);
  await form.getByLabel("대본", { exact: true }).fill("웹 화면에서 만든 첫 번째 문장입니다.\n\n두 번째 문단도 이어서 읽습니다.");
  await form.getByTestId("param-seed").fill("4242");
  await form.getByTestId("tts-params-advanced").locator("summary").click();   // 고급 옵션(접힘)
  await form.getByTestId("param-verify").check();
  await form.getByRole("button", { name: "생성" }).click();
  await expect(page.getByTestId("tts-job")).toHaveAttribute("data-status", "done", { timeout: 14 * 60_000 });
  const gid = await page.getByTestId("tts-result").getAttribute("data-gen-id");
  const g = await (await request.get(API(`/api/generations/${gid}`))).json();
  expect(g.engine).toBe("qwen");
  expect(g.output.duration).toBeGreaterThan(2);
  const sys = await (await request.get(API("/api/settings"))).json();
  if (sys.allowed_gpus) for (const d of g.device) expect(sys.allowed_gpus).toContain(d.uuid);
  console.log("GPU_GEN", JSON.stringify({ id: g.id, device: g.device, timings: g.timings, parts: g.parts.map((p: any) => ({ i: p.i, ...p.checks, attempts: p.attempts })) }));
});
