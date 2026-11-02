#!/usr/bin/env node
// voice 설치·실행 스크립트 — 어느 OS 에서나 node + uv 만 있으면 된다(도커 없음).
//   node scripts/voice.mjs setup    서버 환경(uv sync) + 웹 의존성(npm ci)
//   node scripts/voice.mjs build    웹 빌드(web/dist)
//   node scripts/voice.mjs start    서버를 앞에서 실행(Ctrl+C 로 끝)
//   node scripts/voice.mjs deploy   setup → build → 이전 서버 종료(PID·트리 확인) → 새 서버 백그라운드 기동 → /api/health 확인
//   node scripts/voice.mjs stop     백그라운드 서버 종료
//   node scripts/voice.mjs status   상태
// 환경 변수: VOICE_PORT(8765) · VOICE_HOST(127.0.0.1) · VOICE_DATA_DIR(./data) · VOICE_ENVS_DIR(./envs)
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PORT = process.env.VOICE_PORT || "8765";
const HOST = process.env.VOICE_HOST || "127.0.0.1";
const DATA = path.resolve(process.env.VOICE_DATA_DIR || path.join(ROOT, "data"));
const PIDFILE = path.join(ROOT, ".voice-server.pid");
const WIN = process.platform === "win32";
const URL_ = `http://${HOST === "0.0.0.0" ? "127.0.0.1" : HOST}:${PORT}`;

function run(cmd, args, opts = {}) {
  console.log(`$ ${cmd} ${args.join(" ")}`);
  // Windows 의 npm 은 npm.cmd 라 셸이 필요하다 — 인자를 배열로 셸에 넘기면 Node 가 경고하므로 한 줄로 넘긴다(인자에 공백 없음)
  const r = WIN
    ? spawnSync(`${cmd} ${args.join(" ")}`, { stdio: "inherit", cwd: ROOT, shell: true, ...opts })
    : spawnSync(cmd, args, { stdio: "inherit", cwd: ROOT, ...opts });
  if (r.status !== 0) {
    console.error(`실패(코드 ${r.status}): ${cmd} ${args.join(" ")}`);
    process.exit(r.status || 1);
  }
}

function need(cmd, hint) {
  const r = WIN ? spawnSync(`${cmd} --version`, { shell: true, encoding: "utf8" }) : spawnSync(cmd, ["--version"], { encoding: "utf8" });
  if (r.status !== 0) {
    console.error(`${cmd} 가 없다 — ${hint}`);
    process.exit(1);
  }
  return (r.stdout || "").trim();
}

function setup() {
  console.log("uv", need("uv", "https://docs.astral.sh/uv/getting-started/installation/ 로 설치한다"));
  run("uv", ["sync", "--frozen"]);
  const web = path.join(ROOT, "web");
  // NODE_ENV=production·omit=dev 인 기계(원격 4080x2)에서도 빌드 도구(tsc·vite)를 받는다
  run("npm", ["ci", "--include=dev", "--no-audit", "--no-fund"], { cwd: web });
}

function build() {
  run("npm", ["run", "build"], { cwd: path.join(ROOT, "web") });
}

function alive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function health(timeoutMs) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const r = await fetch(`${URL_}/api/health`);
      if (r.ok) return await r.json();
    } catch {}
    await new Promise((res) => setTimeout(res, 500));
  }
  return null;
}

async function stop() {
  if (!fs.existsSync(PIDFILE)) {
    console.log("실행 중인 서버 기록 없음");
    return true;
  }
  const pid = Number(fs.readFileSync(PIDFILE, "utf8").trim());
  if (pid && alive(pid)) {
    console.log(`서버 종료 PID ${pid} (자식 작업자 포함)`);
    // 엔진 작업자까지 트리째 — PID 로만 죽인다
    if (WIN) spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    else {
      try { process.kill(-pid, "SIGTERM"); } catch {}
      try { process.kill(pid, "SIGTERM"); } catch {}
    }
    for (let i = 0; i < 40 && alive(pid); i++) await new Promise((r) => setTimeout(r, 250));
    if (alive(pid)) {
      console.error(`PID ${pid} 가 아직 살아 있다`);
      return false;
    }
  }
  fs.rmSync(PIDFILE, { force: true });
  // 포트가 풀렸는지 확인
  for (let i = 0; i < 20; i++) {
    if (!(await health(300))) return true;
  }
  console.error(`${URL_} 가 아직 응답한다 — 다른 프로세스가 포트를 쓰고 있다`);
  return false;
}

async function startDetached() {
  fs.mkdirSync(path.join(DATA, "logs"), { recursive: true });
  const logPath = path.join(DATA, "logs", "server.log");
  let pid;
  if (WIN && process.env.SSH_CONNECTION) {
    pid = startViaWmi(logPath);
  } else {
    const log = fs.openSync(logPath, "a");
    const child = spawn("uv", ["run", "--frozen", "voice-server", "--host", HOST, "--port", PORT], {
      cwd: ROOT, detached: true, stdio: ["ignore", log, log], shell: false,
      env: { ...process.env, PYTHONUTF8: "1" }, windowsHide: true,
    });
    child.unref();
    pid = child.pid;
  }
  fs.writeFileSync(PIDFILE, String(pid));
  const h = await health(90_000);
  if (!h) {
    console.error(`서버가 90초 안에 뜨지 않았다 — ${logPath} 를 본다`);
    process.exit(1);
  }
  console.log(`서버 기동 PID ${pid} · ${URL_} · 버전 ${h.service.version} (${h.service.git || "커밋 없음"}) · 데이터 ${h.data_dir}`);
}

// Windows OpenSSH 는 세션의 프로세스를 job object 로 묶어 세션이 끝나면 함께 죽인다(원격 4080x2 실측: 기동 직후 종료).
// SSH 로 배포할 때는 WMI(Win32_Process.Create)로 세션 밖에서 띄운다. 그 프로세스는 지금 환경을 물려받지 않으므로
// uv 절대 경로와 필요한 환경 변수를 명령 줄에 직접 싣는다.
function startViaWmi(logPath) {
  const where = spawnSync("where uv", { shell: true, encoding: "utf8" });
  const uv = (where.stdout || "").split(/\r?\n/).find((l) => l.trim()) || "uv";
  const keep = ["VOICE_DATA_DIR", "VOICE_ENVS_DIR", "VOICE_TEST_ENGINES", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "HF_ENDPOINT", "HF_TOKEN"];
  const sets = keep.filter((k) => process.env[k]).map((k) => `set "${k}=${process.env[k]}"&& `).join("");
  const line = `cmd.exe /c "${sets}set "PATH=${path.dirname(uv)};%PATH%"&& set PYTHONUTF8=1&& "${uv.trim()}" run --frozen voice-server --host ${HOST} --port ${PORT} >> "${logPath}" 2>&1"`;
  const ps = `$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$env:VOICE_CMD; CurrentDirectory=$env:VOICE_CWD}; if ($r.ReturnValue -ne 0) { exit 1 }; $r.ProcessId`;
  const r = spawnSync("powershell", ["-NoProfile", "-Command", ps], {
    encoding: "utf8", env: { ...process.env, VOICE_CMD: line, VOICE_CWD: ROOT },
  });
  const pid = Number((r.stdout || "").trim().split(/\s+/).pop());
  if (r.status !== 0 || !pid) {
    console.error("WMI 기동 실패: " + (r.stderr || r.stdout));
    process.exit(1);
  }
  console.log("SSH 세션 밖에서 기동(WMI)");
  return pid;
}

const cmd = process.argv[2] || "status";
if (cmd === "setup") setup();
else if (cmd === "build") build();
else if (cmd === "start") run("uv", ["run", "--frozen", "voice-server", "--host", HOST, "--port", PORT]);
else if (cmd === "stop") process.exit((await stop()) ? 0 : 1);
else if (cmd === "deploy") {
  setup();
  build();
  if (!(await stop())) process.exit(1);
  await startDetached();
} else if (cmd === "status") {
  const h = await health(1500);
  console.log(h ? `실행 중 ${URL_} · ${JSON.stringify(h.service)}` : "꺼져 있음");
} else {
  console.error(`모르는 명령: ${cmd}`);
  process.exit(2);
}
