import { useEffect, useState } from "react";
import { api, errText, isActive } from "../api";
import type { WorkerInfo } from "../api";
import { Badge, ErrorAlert, JobPanel, JobProgress, JobStatusBadge, KeyValue } from "../components/ui";
import { fmtTime, JOB_KIND } from "../format";
import { useApp, useJob } from "../state";

function Workers() {
  const [ws, setWs] = useState<WorkerInfo[]>([]);
  const [err, setErr] = useState("");
  const [loaded, setLoaded] = useState(false);
  const load = async () => {
    try {
      setWs(await api.get<WorkerInfo[]>("/api/workers"));
      setErr("");
    } catch (e) {
      setErr(errText(e));
    } finally {
      setLoaded(true);
    }
  };
  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 2000);
    return () => clearInterval(t);
  }, []);
  return (
    <section className="card" aria-labelledby="workers-h" data-testid="workers-section">
      <h2 id="workers-h">상주 작업자</h2>
      <p className="small muted">모델을 실은 채 대기하는 엔진 프로세스입니다. 유휴 시간·상주 수 설정에 따라 저절로 내려가며, 여기서 바로 내릴 수도 있습니다.</p>
      <ErrorAlert message={err} />
      {loaded && !ws.length ? (
        <p className="empty" data-testid="workers-empty">
          상주 작업자가 없습니다.
        </p>
      ) : null}
      {ws.length ? (
        <div className="table-wrap">
          <table aria-label="상주 작업자 목록" data-testid="workers-table">
            <thead>
              <tr>
                <th scope="col">PID</th>
                <th scope="col">엔진</th>
                <th scope="col">모델</th>
                <th scope="col">상태</th>
                <th scope="col">장치</th>
                <th scope="col">유휴</th>
                <th scope="col">동작</th>
              </tr>
            </thead>
            <tbody>
              {ws.map((w) => (
                <tr key={w.pid} data-testid="worker-row" data-pid={w.pid}>
                  <th scope="row" className="mono">
                    {w.pid}
                  </th>
                  <td>{w.engine}</td>
                  <td className="mono small">{w.model}</td>
                  <td>
                    {!w.alive ? <Badge tone="bad">죽음</Badge> : w.busy ? <Badge tone="info">작업 중</Badge> : <Badge tone="ok">대기</Badge>}
                    {w.loaded ? " " : null}
                    {w.loaded ? <Badge tone="muted">실림</Badge> : null}
                  </td>
                  <td>{w.gpus?.length ? w.gpus.map((g) => `GPU${g}`).join(", ") : "CPU"}</td>
                  <td className="num">{w.idle_s}s</td>
                  <td>
                    <button
                      type="button"
                      disabled={w.busy}
                      title={w.busy ? "작업 중인 작업자는 그 작업을 취소하세요" : undefined}
                      onClick={async () => {
                        try {
                          await api.post(`/api/workers/${w.pid}/stop`);
                          await load();
                        } catch (e) {
                          setErr(errText(e));
                        }
                      }}
                    >
                      내리기
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function JobResult({ id }: { id: string }) {
  const job = useJob(id);
  if (!job?.result) return null;
  return (
    <details>
      <summary>결과 값</summary>
      <KeyValue data={job.result} label="작업 결과" testid="job-result" />
    </details>
  );
}

export function JobsPage() {
  const { jobs, refreshJobs } = useApp();
  const [sel, setSel] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [onlyActive, setOnlyActive] = useState(false);
  const shown = onlyActive ? jobs.filter(isActive) : jobs;
  return (
    <div className="stack">
      <section className="card" aria-labelledby="jobs-h" data-testid="jobs-section">
        <div className="row wrap gap">
          <h2 id="jobs-h">작업 목록</h2>
          <button type="button" onClick={() => void refreshJobs()}>
            목록 새로 고침
          </button>
          <label className="inline">
            <input type="checkbox" checked={onlyActive} onChange={(e) => setOnlyActive(e.target.checked)} />
            진행 중인 것만
          </label>
          <span className="small muted">서버가 다시 켜지면 지난 작업은 목록에서 빠집니다(기록은 남음).</span>
        </div>
        <ErrorAlert message={err} />
        {!shown.length ? (
          <p className="empty" data-testid="jobs-empty">
            작업이 없습니다.
          </p>
        ) : (
          <div className="table-wrap">
            <table aria-label="작업 목록" data-testid="jobs-table">
              <thead>
                <tr>
                  <th scope="col">종류</th>
                  <th scope="col">제목</th>
                  <th scope="col">상태</th>
                  <th scope="col">단계</th>
                  <th scope="col">진행률</th>
                  <th scope="col">장치</th>
                  <th scope="col">시각</th>
                  <th scope="col">동작</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((j) => (
                  <tr key={j.id} data-testid="job-row" data-job-id={j.id} data-kind={j.kind} data-status={j.status} aria-selected={sel === j.id}>
                    <td>{JOB_KIND[j.kind] ?? j.kind}</td>
                    <th scope="row">
                      {j.title}
                      <div className="mono small muted">{j.id}</div>
                      {j.cancel_note ? <div className="small">취소 기록: {j.cancel_note}</div> : null}
                      {j.error ? <div className="small bad-text">{j.error.slice(0, 160)}</div> : null}
                    </th>
                    <td>
                      <JobStatusBadge job={j} />
                    </td>
                    <td className="small">{j.stage}</td>
                    <td>
                      <JobProgress job={j} />
                    </td>
                    <td>{j.devices?.length ? j.devices.map((d) => (d === "cpu" ? "CPU" : `GPU${d}`)).join(", ") : "—"}</td>
                    <td className="small">
                      <div>만듦 {fmtTime(j.created)}</div>
                      {j.finished ? <div>끝남 {fmtTime(j.finished)}</div> : null}
                    </td>
                    <td>
                      <div className="row gap wrap">
                        <button type="button" onClick={() => setSel(sel === j.id ? null : j.id)} aria-pressed={sel === j.id}>
                          로그
                        </button>
                        {isActive(j) ? (
                          <button
                            type="button"
                            className="danger"
                            onClick={async () => {
                              try {
                                await api.post(`/api/jobs/${j.id}/cancel`);
                                await refreshJobs();
                              } catch (e) {
                                setErr(errText(e));
                              }
                            }}
                          >
                            취소
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {sel ? (
        <section className="card" aria-label="작업 상세" data-testid="job-detail">
          <div className="row wrap gap">
            <h2>작업 상세</h2>
            <button type="button" onClick={() => setSel(null)}>
              상세 닫기
            </button>
          </div>
          <JobPanel jobId={sel} testid="job-detail-panel" logOpen />
          <JobResult id={sel} />
        </section>
      ) : null}
      <Workers />
    </div>
  );
}
