import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api, errText, isFinished } from "../api";
import type { Catalog, Commercial, Job, ParamSpec, ParamValue, Params, Upload } from "../api";
import { commercialInfo, fmtBytes, fmtSec, JOB_STATUS } from "../format";
import { useApp, useJob } from "../state";

export function ErrorAlert({ message, testid }: { message: string; testid?: string }) {
  if (!message) return null;
  return (
    <p role="alert" className="alert" data-testid={testid ?? "error-alert"}>
      {message}
    </p>
  );
}

export function Badge({ tone, children, testid, title }: { tone: "ok" | "bad" | "warn" | "muted" | "info"; children: ReactNode; testid?: string; title?: string }) {
  return (
    <span className={`badge badge-${tone}`} data-testid={testid} title={title}>
      {children}
    </span>
  );
}

export function CommercialBadge({ value, license }: { value: Commercial; license?: string }) {
  const c = commercialInfo(value);
  return (
    <span className="badge-line">
      {license ? <span className="license">{license}</span> : null}
      <Badge tone={c.tone} testid="commercial-badge" title={license}>
        <span data-commercial={c.key}>{c.text}</span>
      </Badge>
    </span>
  );
}

/** 지우기처럼 되돌릴 수 없는 동작 — 두 번 눌러 확인(브라우저 confirm 창을 쓰지 않는다: 헤드리스 시험이 막힌다). */
export function ConfirmButton({ label, confirmLabel, onConfirm, disabled }: { label: string; confirmLabel?: string; onConfirm: () => void | Promise<void>; disabled?: boolean }) {
  const [asking, setAsking] = useState(false);
  if (!asking)
    return (
      <button type="button" className="danger" onClick={() => setAsking(true)} disabled={disabled}>
        {label}
      </button>
    );
  return (
    <span className="confirm" role="group" aria-label={`${label} 확인`}>
      <button
        type="button"
        className="danger solid"
        onClick={async () => {
          setAsking(false);
          await onConfirm();
        }}
      >
        {confirmLabel ?? `${label} 확인`}
      </button>
      <button type="button" onClick={() => setAsking(false)}>
        그만두기
      </button>
    </span>
  );
}

function statusTone(s: Job["status"]): "ok" | "bad" | "warn" | "info" | "muted" {
  if (s === "done") return "ok";
  if (s === "error") return "bad";
  if (s === "cancelled") return "muted";
  if (s === "running" || s === "loading") return "info";
  return "warn";
}

export function JobStatusBadge({ job }: { job: Pick<Job, "status"> }) {
  return (
    <Badge tone={statusTone(job.status)} testid="job-status">
      <span data-status={job.status}>{JOB_STATUS[job.status] ?? job.status}</span>
    </Badge>
  );
}

export function JobProgress({ job }: { job: Job }) {
  const pct = Math.round((job.progress || 0) * 100);
  return (
    <span className="progress-wrap">
      <progress aria-label={`진행률 ${job.title}`} max={1} value={job.progress || 0} data-testid="job-progress" />
      <span className="mono small">{pct}%</span>
    </span>
  );
}

/** 작업 하나의 진행·단계·로그·취소. 끝나면 onDone 을 한 번 부른다. */
export function JobPanel({ jobId, onDone, testid, logOpen }: { jobId: string | null; onDone?: (j: Job) => void; testid: string; logOpen?: boolean }) {
  const job = useJob(jobId);
  const { refreshJobs } = useApp();
  const doneFor = useRef<string | null>(null);
  // 새 작업이 생기면 상단 「실행 중 작업」 수를 바로 맞춘다(전역 폴링을 기다리지 않음)
  useEffect(() => {
    if (jobId) void refreshJobs();
  }, [jobId, refreshJobs]);
  const [err, setErr] = useState("");
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;
  useEffect(() => {
    if (job && isFinished(job) && doneFor.current !== job.id) {
      doneFor.current = job.id;
      onDoneRef.current?.(job);
      void refreshJobs();
    }
  }, [job, refreshJobs]);
  if (!jobId) return null;
  if (!job)
    return (
      <section className="job-panel" data-testid={testid} aria-label="작업 진행" aria-busy="true">
        <p role="status">작업 정보를 불러오는 중…</p>
      </section>
    );
  const finished = isFinished(job);
  return (
    <section className="job-panel" data-testid={testid} data-job-id={job.id} data-status={job.status} aria-label={`작업 진행: ${job.title}`} aria-busy={!finished}>
      <div className="row wrap gap">
        <strong>{job.title}</strong>
        <JobStatusBadge job={job} />
        {job.devices?.length ? <span className="muted small">장치: {job.devices.map((d) => (d === "cpu" ? "CPU" : `GPU${d}`)).join(", ")}</span> : null}
      </div>
      <p role="status" className="stage" data-testid="job-stage">
        {job.stage}
      </p>
      <JobProgress job={job} />
      {job.bytes ? (
        <p className="small mono" data-testid="job-bytes">
          {fmtBytes(job.bytes[0])} / {fmtBytes(job.bytes[1])}
        </p>
      ) : null}
      <ErrorAlert message={job.error} testid="job-error" />
      {job.cancel_note ? (
        <p className="small" data-testid="job-cancel-note">
          취소 기록: {job.cancel_note}
        </p>
      ) : null}
      {!finished ? (
        <button
          type="button"
          className="danger"
          onClick={async () => {
            try {
              await api.post(`/api/jobs/${job.id}/cancel`);
              setErr("");
            } catch (e) {
              setErr(errText(e));
            }
          }}
        >
          작업 취소
        </button>
      ) : null}
      <ErrorAlert message={err} />
      <details open={logOpen}>
        <summary>로그 ({job.log?.length ?? 0}줄)</summary>
        <pre className="log" data-testid="job-log" tabIndex={0} aria-label="작업 로그">
          {(job.log ?? []).join("\n") || (finished ? "(로그 없음)" : "(아직 로그 없음)")}
        </pre>
      </details>
    </section>
  );
}

/** 카탈로그 파라미터 스키마로 입력 칸을 만든다. basic 은 늘 보이고 advanced 는 접는다. */
export function ParamFields({ specs, values, onChange, exclude = [], testid = "param-fields" }: { specs: ParamSpec[]; values: Params; onChange: (key: string, v: ParamValue) => void; exclude?: string[]; testid?: string }) {
  const prefix = useId();
  const shown = specs.filter((s) => !exclude.includes(s.key));
  const basic = shown.filter((s) => s.group === "basic");
  const adv = shown.filter((s) => s.group !== "basic");
  const field = (p: ParamSpec) => {
    const id = `${prefix}-${p.key}`;
    const helpId = p.help ? `${id}-help` : undefined;
    const v = values[p.key] ?? p.default;
    let control: ReactNode;
    if (p.type === "bool") {
      control = <input id={id} type="checkbox" checked={!!v} onChange={(e) => onChange(p.key, e.target.checked)} aria-describedby={helpId} data-testid={`param-${p.key}`} />;
    } else if (p.type === "select") {
      control = (
        <select id={id} value={String(v)} onChange={(e) => onChange(p.key, e.target.value)} aria-describedby={helpId} data-testid={`param-${p.key}`}>
          {(p.options ?? []).map(([val, name]) => (
            <option key={val} value={val}>
              {name}
            </option>
          ))}
        </select>
      );
    } else if (p.type === "int" || p.type === "float") {
      control = (
        <input
          id={id}
          type="number"
          min={p.min}
          max={p.max}
          step={p.step ?? (p.type === "int" ? 1 : "any")}
          value={v === "" ? "" : String(v)}
          onChange={(e) => onChange(p.key, e.target.value === "" ? "" : Number(e.target.value))}
          aria-describedby={helpId}
          data-testid={`param-${p.key}`}
        />
      );
    } else {
      control = <input id={id} type="text" value={String(v)} onChange={(e) => onChange(p.key, e.target.value)} aria-describedby={helpId} data-testid={`param-${p.key}`} />;
    }
    return (
      <div className={`field ${p.type === "bool" ? "field-check" : ""}`} key={p.key}>
        {p.type === "bool" ? (
          <>
            {control}
            <label htmlFor={id}>{p.label}</label>
          </>
        ) : (
          <>
            <label htmlFor={id}>{p.label}</label>
            {control}
          </>
        )}
        {p.help ? (
          <small id={helpId} className="help">
            {p.help}
          </small>
        ) : null}
      </div>
    );
  };
  return (
    <div data-testid={testid} className="params">
      {basic.length ? (
        <fieldset>
          <legend>기본 설정</legend>
          <div className="grid-fields">{basic.map(field)}</div>
        </fieldset>
      ) : null}
      {adv.length ? (
        <details className="advanced" data-testid={`${testid}-advanced`}>
          <summary>고급 설정 ({adv.length})</summary>
          <div className="grid-fields">{adv.map(field)}</div>
        </details>
      ) : null}
      {!shown.length ? <p className="muted small">이 엔진은 따로 고를 설정이 없습니다.</p> : null}
    </div>
  );
}

/** 제출 직전: 비운 숫자 칸은 기본값, 문자열 숫자는 숫자로. */
export function cleanParams(specs: ParamSpec[], values: Params): Params {
  const out: Params = {};
  for (const p of specs) {
    let v = values[p.key];
    if (v === undefined || v === "") v = p.default;
    if (p.type === "int") v = Math.round(Number(v));
    else if (p.type === "float") v = Number(v);
    if ((p.type === "int" || p.type === "float") && Number.isNaN(v as number)) v = p.default;
    out[p.key] = v;
  }
  return out;
}

export function ModelSelect({ catalog, kind, value, onChange, label, testid }: { catalog: Catalog; kind: "tts" | "asr"; value: string; onChange: (id: string) => void; label: string; testid: string }) {
  const id = useId();
  const engines = Object.values(catalog.engines).filter((e) => e.kind === kind);
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid}>
        {!catalog.models[value] ? <option value="">— 고르세요 —</option> : null}
        {engines.map((e) => (
          <optgroup key={e.key} label={e.label}>
            {e.models
              .filter((m) => catalog.models[m])
              .map((m) => {
                const mm = catalog.models[m];
                const tag = [mm.check.ok ? "" : "미준비", mm.commercial === true ? "" : commercialInfo(mm.commercial).text].filter(Boolean).join(" · ");
                return (
                  <option key={m} value={m}>
                    {mm.label}
                    {tag ? ` (${tag})` : ""}
                  </option>
                );
              })}
          </optgroup>
        ))}
      </select>
    </div>
  );
}

/** 음성 업로드 + 이미 올린 파일 고르기 + 재생. */
export function UploadPicker({ value, onChange, testid, legend }: { value: string; onChange: (id: string, u: Upload | null) => void; testid: string; legend: string }) {
  const id = useId();
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const reload = async () => {
    try {
      const list = await api.get<Upload[]>("/api/uploads");
      setUploads(list);
      return list;
    } catch (e) {
      setErr(errText(e));
      return [];
    }
  };
  useEffect(() => {
    void reload();
  }, []);
  const sel = uploads.find((u) => u.id === value) ?? null;
  return (
    <fieldset data-testid={testid} className="upload-picker">
      <legend>{legend}</legend>
      <div className="row wrap gap">
        <div className="field">
          <label htmlFor={`${id}-file`}>음성 파일 올리기</label>
          <input
            id={`${id}-file`}
            type="file"
            accept="audio/*,video/*,.wav,.mp3,.m4a,.flac,.ogg,.mp4,.webm"
            disabled={busy}
            data-testid={`${testid}-file`}
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              setBusy(true);
              setErr("");
              setMsg("");
              try {
                const u = await api.upload(f);
                await reload();
                onChange(u.id, u);
                setMsg(`올림: ${u.name} (${fmtSec(u.duration)})`);
              } catch (ex) {
                setErr(errText(ex));
              } finally {
                setBusy(false);
                e.target.value = "";
              }
            }}
          />
        </div>
        <div className="field grow">
          <label htmlFor={`${id}-sel`}>올린 음성 고르기</label>
          <select
            id={`${id}-sel`}
            value={value}
            data-testid={`${testid}-select`}
            onChange={(e) => onChange(e.target.value, uploads.find((u) => u.id === e.target.value) ?? null)}
          >
            <option value="">— 고르세요 ({uploads.length}개) —</option>
            {uploads.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name} · {fmtSec(u.duration)} · {u.id}
              </option>
            ))}
          </select>
        </div>
      </div>
      {busy ? <p role="status">올리는 중…</p> : null}
      {msg ? (
        <p role="status" className="small" data-testid={`${testid}-status`}>
          {msg}
        </p>
      ) : null}
      <ErrorAlert message={err} />
      {sel ? (
        <div className="row wrap gap">
          <audio controls preload="none" src={`/api/uploads/${sel.id}/audio`} aria-label={`올린 음성 재생: ${sel.name}`} data-testid={`${testid}-audio`} />
          <span className="small muted">
            {sel.sr ? `${sel.sr} Hz · ` : ""}
            {fmtBytes(sel.bytes)}
          </span>
        </div>
      ) : null}
    </fieldset>
  );
}

export function KeyValue({ data, testid, label }: { data: Record<string, unknown> | null | undefined; testid?: string; label: string }) {
  const entries = Object.entries(data ?? {});
  return (
    <table className="kv" data-testid={testid} aria-label={label}>
      <tbody>
        {entries.length ? (
          entries.map(([k, v]) => (
            <tr key={k}>
              <th scope="row">{k}</th>
              <td className="mono">{typeof v === "object" && v !== null ? JSON.stringify(v) : String(v)}</td>
            </tr>
          ))
        ) : (
          <tr>
            <td colSpan={2} className="muted">
              (없음)
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
