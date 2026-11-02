// 서버 계약: docs/api.md. 오류 본문은 {"detail": "사람 말"}.

export type ParamType = "int" | "float" | "bool" | "select" | "text";
export type ParamValue = number | boolean | string;
export type Params = Record<string, ParamValue>;

export interface ParamSpec {
  key: string;
  label: string;
  type: ParamType;
  default: ParamValue;
  help?: string;
  group: "basic" | "advanced";
  min?: number;
  max?: number;
  step?: number;
  options?: [string, string][];
}

export type Commercial = boolean | "limited" | null;

export interface Engine {
  key: string;
  kind: "tts" | "asr";
  label: string;
  env: string;
  languages: string[];
  batch?: boolean;
  deterministic?: boolean;
  use: string;
  caveat: string;
  models: string[];
  common: ParamSpec[];
  params: ParamSpec[];
  cpu_ok?: boolean;
  test?: boolean;
}

export interface ModelCheck {
  ok: boolean;
  path: string;
  missing: string[];
  size_gb: number;
  error?: string;
  custom?: boolean;
}

export interface Model {
  id: string;
  engine: string;
  kind: "tts" | "asr" | "aux";
  repo: string;
  label: string;
  size_gb: number;
  vram_gb?: number;
  gpus: number;
  license: string;
  commercial: Commercial;
  requires: string[];
  measured?: string;
  default?: boolean;
  builtin?: boolean;
  location: string;
  check: ModelCheck;
}

export interface EnvStatus {
  env: string;
  installed: boolean;
  has_manifest?: boolean;
  builtin?: boolean;
  python?: string;
  torch?: string;
  installed_at?: string;
  freeze_sha?: string;
}

export interface Catalog {
  languages: Record<string, string>;
  engines: Record<string, Engine>;
  models: Record<string, Model>;
  envs: Record<string, EnvStatus>;
  defaults: { tts_model: string; asr_model: string };
}

export type JobStatus = "queued" | "waiting" | "loading" | "running" | "done" | "error" | "cancelled";

export interface Job {
  id: string;
  kind: "tts" | "asr" | "ref" | "env" | "download" | "load";
  title: string;
  status: JobStatus;
  stage: string;
  progress: number;
  created: number;
  started: number | null;
  finished: number | null;
  error: string;
  devices: (number | string)[];
  result: Record<string, unknown> | null;
  cancel_note: string;
  bytes?: [number, number];
  log?: string[];
}

export interface Upload {
  id: string;
  name: string;
  file: string;
  bytes: number;
  sha256: string;
  sr?: number;
  duration?: number;
  channels?: number;
  created: number;
}

export type ConsentBasis = "self" | "other_consent" | "licensed" | "synthetic";

export interface RefSet {
  id: string;
  name: string;
  rev: number;
  mode: "auto" | "manual";
  picked: string;
  upload: { id: string; name: string; sha256?: string; duration?: number };
  language: string;
  text: string;
  auto_text: string;
  window: [number, number];
  cut: [number, number];
  clip_duration: number;
  f0_median: number | null;
  clip_sha256: string;
  consent: { basis: ConsentBasis; note: string; agreed: boolean; agreed_at?: string };
  created: number;
}

export interface PartChecks {
  basic?: string;
  lead_low_s?: number;
  match?: number;
  heard?: string;
  failed?: boolean;
  verify_model?: string;
}

export interface GenPart {
  i: number;
  text: string;
  seed: number;
  seed_used?: number;
  file: string;
  dur?: number;
  infer_s?: number;
  attempts: number;
  checks: PartChecks;
}

export interface Generation {
  id: string;
  name: string;
  kind: "tts";
  status: "ok" | "warn";
  engine: string;
  engine_label: string;
  model: Record<string, unknown> & { id: string };
  model_label: string;
  license: string;
  commercial: Commercial;
  aux_models: Record<string, unknown>[];
  env: Record<string, string>;
  service: { version: string; git: string; dirty: boolean };
  device: { index?: number; name: string; uuid?: string }[];
  language: string;
  text: string;
  text_used: string;
  params: Params;
  seed: number;
  ref: Partial<RefSet> & { id?: string; clip_sha256?: string; from_generation?: string };
  parts: GenPart[];
  output: { file: string; sr?: number; duration: number; sha256: string };
  timings: Record<string, number>;
  created: number;
}

export interface Segment {
  start: number;
  end: number;
  text: string;
  words?: { start: number; end: number; word: string; prob: number }[];
}

export interface Transcript {
  id: string;
  name: string;
  kind: "asr";
  upload: { id: string; name: string; duration?: number; sha256?: string };
  engine: string;
  engine_label: string;
  model: Record<string, unknown> & { id: string };
  model_label: string;
  language_requested?: string;
  language: string;
  params: Params;
  segments: Segment[];
  segment_count?: number;
  device: { index?: number; name: string }[];
  timings: Record<string, number>;
  edited?: boolean;
  created: number;
}

export interface Gpu {
  index: number;
  name: string;
  uuid: string;
  total_gb: number;
  used_gb: number;
  free_gb: number;
  temp_c: number | null;
  util: number | null;
  allowed: boolean;
  blocked: string[];
  ours_gb: number;
  foreign_est_gb: number;
}

export interface WorkerInfo {
  engine: string;
  model: string;
  pid: number;
  alive: boolean;
  busy: boolean;
  loaded: boolean;
  gpus: number[];
  idle_s: number;
  log: string;
}

export interface SystemInfo {
  os: string;
  machine: string;
  cpu: string;
  cpu_count: number;
  cpu_physical: number;
  ram_gb: number;
  ram_free_gb: number;
  cpu_percent: number;
  gpus: Gpu[];
  workers: WorkerInfo[];
  service: { version: string; git: string; dirty: boolean };
  data_dir: string;
}

export interface Settings {
  model_root: string;
  model_paths: Record<string, string>;
  gpu_mode: "auto" | "cpu";
  allowed_gpus: string[] | null;
  vram_reserve_gb: number;
  avoid_foreign_gpu: boolean;
  foreign_vram_gb: number;
  temp_limit_c: number;
  allow_cpu: boolean;
  cpu_threads: number;
  idle_unload_min: number;
  max_resident: number;
  hf_endpoint: string;
  show_test_engines: boolean;
  default_tts_model: string;
  default_asr_model: string;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function detailText(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      // FastAPI 검증 오류(422)
      return d
        .map((e) => {
          const o = e as { loc?: unknown[]; msg?: string };
          return `${(o.loc || []).join(".")}: ${o.msg ?? ""}`;
        })
        .join("; ");
    }
    return JSON.stringify(d);
  }
  return `요청 실패 (HTTP ${status})`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "서버에 연결할 수 없습니다 — voice-server 가 켜져 있는지 확인하세요");
  }
  const text = await res.text();
  let parsed: unknown = undefined;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  if (!res.ok) throw new ApiError(res.status, detailText(parsed, res.status));
  return parsed as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body ?? {}),
  del: <T>(path: string) => request<T>("DELETE", path),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<Upload>("POST", "/api/uploads", fd);
  },
};

export function errText(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

export const FINISHED: JobStatus[] = ["done", "error", "cancelled"];
export const isFinished = (j: Job | null | undefined) => !!j && FINISHED.includes(j.status);
export const isActive = (j: Job) => !FINISHED.includes(j.status);

export function paramDefaults(specs: ParamSpec[]): Params {
  const out: Params = {};
  for (const p of specs) out[p.key] = p.default;
  return out;
}
