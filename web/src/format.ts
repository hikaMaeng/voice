import type { Commercial, ConsentBasis, JobStatus } from "./api";

export function fmtTime(epoch: number | null | undefined): string {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleString("ko-KR", { hour12: false });
}

/** 초 → m:ss.s */
export function fmtSec(s: number | null | undefined, digits = 1): string {
  if (s === null || s === undefined || Number.isNaN(s)) return "—";
  const neg = s < 0;
  const a = Math.abs(s);
  const m = Math.floor(a / 60);
  const rest = a - m * 60;
  const ss = rest.toFixed(digits).padStart(digits ? 3 + digits : 2, "0");
  return `${neg ? "-" : ""}${m}:${ss}`;
}

export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i ? 1 : 0)} ${u[i]}`;
}

export function fmtGb(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : `${n} GB`;
}

export const JOB_STATUS: Record<JobStatus, string> = {
  queued: "대기열",
  waiting: "자원 대기",
  loading: "모델 싣는 중",
  running: "실행 중",
  done: "완료",
  error: "실패",
  cancelled: "취소됨",
};

export const JOB_KIND: Record<string, string> = {
  tts: "TTS 생성",
  asr: "ASR 전사",
  ref: "참조 세트",
  env: "환경 설치",
  download: "모델 받기",
  load: "미리 싣기",
};

export const CONSENT: Record<ConsentBasis, string> = {
  self: "본인 목소리",
  other_consent: "당사자 동의 받음",
  licensed: "사용권 있음",
  synthetic: "합성 목소리",
};

export function commercialInfo(c: Commercial): { text: string; tone: "ok" | "bad" | "warn" | "muted"; key: string } {
  if (c === true) return { text: "상업 가능", tone: "ok", key: "yes" };
  if (c === false) return { text: "상업 불가", tone: "bad", key: "no" };
  if (c === "limited") return { text: "조건부", tone: "warn", key: "limited" };
  return { text: "확인 필요", tone: "muted", key: "unknown" };
}

export function langName(langs: Record<string, string>, code: string | null | undefined): string {
  if (!code) return "—";
  if (code === "auto") return "자동 감지";
  return langs[code] ? `${langs[code]} (${code})` : code;
}
