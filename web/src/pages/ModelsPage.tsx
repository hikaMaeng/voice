import { useId, useState } from "react";
import { api, errText, isActive } from "../api";
import type { Engine, Job, Model, ModelCheck } from "../api";
import { Badge, CommercialBadge, ErrorAlert, JobPanel } from "../components/ui";
import { fmtGb } from "../format";
import { useApp } from "../state";

const KIND: Record<string, string> = { tts: "TTS", asr: "ASR", aux: "보조" };

function ModelStatus({ m }: { m: Model }) {
  const c = m.check;
  const state = m.builtin ? "builtin" : c.ok ? "ok" : c.missing?.length ? "missing" : "error";
  return (
    <div data-testid="model-status" data-state={state}>
      {m.builtin ? (
        <Badge tone="ok">내장</Badge>
      ) : c.ok ? (
        <Badge tone="ok">준비됨</Badge>
      ) : c.missing?.length ? (
        <Badge tone="warn">파일 없음</Badge>
      ) : (
        <Badge tone="bad">없음</Badge>
      )}
      {!c.ok && c.missing?.length ? <div className="small">빠진 파일: {c.missing.join(", ")}</div> : null}
      {!c.ok && c.error ? <div className="small muted">{c.error}</div> : null}
      {c.ok && !m.builtin ? <div className="small muted">{c.size_gb} GB 확인</div> : null}
    </div>
  );
}

function PathForm({ m, onSaved, onClose }: { m: Model; onSaved: () => void; onClose: () => void }) {
  const id = useId();
  const [path, setPath] = useState(m.check.custom ? m.location : "");
  const [err, setErr] = useState("");
  const [res, setRes] = useState<ModelCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async (p: string) => {
    setBusy(true);
    setErr("");
    try {
      const r = await api.put<ModelCheck>(`/api/models/${m.id}/path`, { path: p });
      setRes(r);
      onSaved();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="path-form"
      aria-label={`${m.label} 위치 지정`}
      data-testid="model-path-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save(path);
      }}
    >
      <div className="field grow">
        <label htmlFor={id}>이미 받은 모델 폴더 경로</label>
        <input id={id} type="text" value={path} placeholder={m.location} onChange={(e) => setPath(e.target.value)} aria-describedby={`${id}-help`} data-testid="model-path-input" />
        <small id={`${id}-help`} className="help">
          비워 두고 저장하면 기본 위치(모델 루트 아래 저장소 이름)로 돌아갑니다.
        </small>
      </div>
      <div className="row gap wrap">
        <button type="submit" className="primary" disabled={busy}>
          위치 저장
        </button>
        <button type="button" disabled={busy} onClick={() => void save("")}>
          기본 위치로
        </button>
        <button type="button" onClick={onClose}>
          닫기
        </button>
      </div>
      {res ? (
        <p role="status" data-testid="model-path-result">
          {res.ok ? "확인됨" : `확인 실패: ${res.error ?? ""}`} — {res.path}
        </p>
      ) : null}
      <ErrorAlert message={err} />
    </form>
  );
}

function ModelRow({ m, jobId, onDownload, refresh }: { m: Model; jobId: string | null; onDownload: (m: Model) => void; refresh: () => void }) {
  const [editing, setEditing] = useState(false);
  const { catalog, jobs } = useApp();
  const running = !!jobId && jobs.some((j) => j.id === jobId && isActive(j));
  return (
    <>
      <tr data-testid="model-row" data-model-id={m.id} data-kind={m.kind}>
        <th scope="row">
          <div className="model-name">{m.label}</div>
          <div className="mono small muted">{m.id}</div>
          {m.default ? <Badge tone="info">기본</Badge> : null}
          {m.requires?.length ? (
            <div className="small">
              보조: {m.requires.map((r) => catalog?.models[r]?.label ?? r).join(", ")}
            </div>
          ) : null}
        </th>
        <td>{KIND[m.kind]}</td>
        <td className="mono small">{m.repo ? <a href={`https://huggingface.co/${m.repo}`} target="_blank" rel="noreferrer">{m.repo}</a> : "—"}</td>
        <td className="num">{m.builtin ? "—" : fmtGb(m.size_gb)}</td>
        <td className="num">{m.vram_gb ? fmtGb(m.vram_gb) : "—"}</td>
        <td className="num">{m.gpus}</td>
        <td>
          <CommercialBadge value={m.commercial} license={m.license} />
        </td>
        <td className="small" data-testid="model-measured">
          {m.measured ?? "—"}
        </td>
        <td>
          <ModelStatus m={m} />
        </td>
        <td className="mono small path-cell" data-testid="model-location">
          {m.location}
          {m.check.custom ? (
            <div>
              <Badge tone="info">직접 지정</Badge>
            </div>
          ) : null}
        </td>
        <td>
          <div className="row gap wrap">
            <button type="button" disabled={m.builtin || running} onClick={() => onDownload(m)}>
              받기
            </button>
            <button type="button" disabled={m.builtin} aria-expanded={editing} onClick={() => setEditing((v) => !v)}>
              위치 지정
            </button>
          </div>
        </td>
      </tr>
      {jobId || editing ? (
        <tr className="subrow" data-testid="model-subrow" data-model-id={m.id}>
          <td colSpan={11}>
            {jobId ? (
              <JobPanel
                jobId={jobId}
                testid="model-download-job"
                onDone={() => {
                  refresh();
                }}
              />
            ) : null}
            {editing ? <PathForm m={m} onSaved={refresh} onClose={() => setEditing(false)} /> : null}
          </td>
        </tr>
      ) : null}
    </>
  );
}

function EnvBox({ e, jobId, onInstall }: { e: Engine; jobId: string | null; onInstall: (env: string) => void }) {
  const { catalog, refreshCatalog, jobs } = useApp();
  const st = catalog?.envs[e.env];
  const running = !!jobId && jobs.some((j) => j.id === jobId && isActive(j));
  const installed = !!st?.installed;
  return (
    <div className="env-box" data-testid="env-status" data-env={e.env} data-installed={installed}>
      <span>
        엔진 환경 <span className="mono">{e.env}</span>:{" "}
        {installed ? <Badge tone="ok">설치됨</Badge> : <Badge tone="warn">미설치</Badge>}
      </span>
      {st?.python ? <span className="small muted">Python {st.python}</span> : null}
      {st?.torch ? <span className="small muted">torch {st.torch}</span> : null}
      {st?.installed_at ? <span className="small muted">설치 {st.installed_at}</span> : null}
      {st?.freeze_sha ? <span className="small muted mono">freeze {String(st.freeze_sha).slice(0, 12)}</span> : null}
      {!st?.builtin ? (
        <button
          type="button"
          disabled={running || st?.has_manifest === false}
          title={st?.has_manifest === false ? "설치 정의(engines/envs/<env>/env.json)가 아직 없습니다" : undefined}
          onClick={() => onInstall(e.env)}
        >
          {installed ? "환경 다시 설치" : "환경 설치"}
        </button>
      ) : (
        <span className="small muted">(서버 내장)</span>
      )}
      {st?.has_manifest === false && !st?.builtin ? <span className="small muted">설치 정의 없음</span> : null}
      {jobId ? <JobPanel jobId={jobId} testid="env-install-job" logOpen onDone={() => void refreshCatalog()} /> : null}
    </div>
  );
}

export function ModelsPage() {
  const { catalog, refreshCatalog, catalogLoading, jobs } = useApp();
  const [filter, setFilter] = useState<"all" | "tts" | "asr">("all");
  const [dlJobs, setDlJobs] = useState<Record<string, string>>({});
  const [envJobs, setEnvJobs] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  if (!catalog) return null;

  const activeByTitle = (title: string, kind: Job["kind"]) => jobs.find((j) => j.kind === kind && j.title === title && isActive(j))?.id ?? null;
  const dlJobFor = (m: Model) => dlJobs[m.id] ?? activeByTitle(`받기 ${m.label}`, "download");
  const envJobFor = (env: string) => envJobs[env] ?? activeByTitle(`환경 설치 ${env}`, "env");

  const download = async (m: Model) => {
    setErr("");
    try {
      const j = await api.post<Job>(`/api/models/${m.id}/download`);
      setDlJobs((s) => ({ ...s, [m.id]: j.id }));
    } catch (e) {
      setErr(`${m.label} 받기 실패: ${errText(e)}`);
    }
  };
  const install = async (env: string) => {
    setErr("");
    try {
      const j = await api.post<Job>(`/api/envs/${env}/install`);
      setEnvJobs((s) => ({ ...s, [env]: j.id }));
    } catch (e) {
      setErr(`환경 ${env} 설치 실패: ${errText(e)}`);
    }
  };
  const engines = Object.values(catalog.engines).filter((e) => filter === "all" || e.kind === filter);
  const models = Object.values(catalog.models);

  return (
    <div className="stack">
      <div className="row wrap gap toolbar">
        <fieldset className="seg" aria-label="종류 거르기">
          <legend className="sr-only">종류 거르기</legend>
          {(
            [
              ["all", "전체"],
              ["tts", "TTS"],
              ["asr", "ASR"],
            ] as const
          ).map(([k, l]) => (
            <label key={k}>
              <input type="radio" name="model-filter" value={k} checked={filter === k} onChange={() => setFilter(k)} />
              {l}
            </label>
          ))}
        </fieldset>
        <button type="button" onClick={() => void refreshCatalog()} disabled={catalogLoading}>
          상태 새로 고침
        </button>
        {catalogLoading ? (
          <span role="status" className="small" data-testid="catalog-loading">
            모델 상태 확인 중…
          </span>
        ) : null}
        <span className="small muted">
          모델 {models.filter((m) => m.kind !== "aux").length}개 · 보조 {models.filter((m) => m.kind === "aux").length}개 · 준비됨 {models.filter((m) => m.check.ok).length}개
        </span>
      </div>
      <ErrorAlert message={err} testid="models-error" />
      {engines.map((e) => {
        const ms = models.filter((m) => m.engine === e.key);
        const hid = `engine-${e.key}-title`;
        return (
          <section key={e.key} className="card" aria-labelledby={hid} data-testid="engine-section" data-engine={e.key}>
            <div className="row wrap gap">
              <h2 id={hid}>{e.label}</h2>
              <Badge tone="info">{e.kind.toUpperCase()}</Badge>
              {e.test ? <Badge tone="warn">시험용</Badge> : null}
              {e.deterministic ? <Badge tone="muted">결정적</Badge> : null}
              {e.batch ? <Badge tone="muted">묶음 생성</Badge> : null}
              {e.cpu_ok ? <Badge tone="muted">CPU 가능</Badge> : null}
            </div>
            <p data-testid="engine-use">
              <strong>쓸 곳:</strong> {e.use || "—"}
            </p>
            {e.caveat ? (
              <p data-testid="engine-caveat" className="caveat">
                <strong>주의:</strong> {e.caveat}
              </p>
            ) : null}
            <EnvBox e={e} jobId={envJobFor(e.env)} onInstall={install} />
            <div className="table-wrap">
              <table aria-label={`${e.label} 모델`} data-testid="models-table">
                <thead>
                  <tr>
                    <th scope="col">이름</th>
                    <th scope="col">종류</th>
                    <th scope="col">저장소</th>
                    <th scope="col">크기</th>
                    <th scope="col">VRAM</th>
                    <th scope="col">카드</th>
                    <th scope="col">라이선스</th>
                    <th scope="col">실측</th>
                    <th scope="col">상태</th>
                    <th scope="col">위치</th>
                    <th scope="col">동작</th>
                  </tr>
                </thead>
                <tbody>
                  {ms.map((m) => (
                    <ModelRow key={m.id} m={m} jobId={dlJobFor(m)} onDownload={download} refresh={() => void refreshCatalog()} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}
