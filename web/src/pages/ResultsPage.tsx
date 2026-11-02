import { useEffect, useId, useState } from "react";
import { api, errText } from "../api";
import type { Generation } from "../api";
import { Badge, CommercialBadge, ConfirmButton, ErrorAlert, KeyValue } from "../components/ui";
import { CONSENT, fmtSec, fmtTime, langName } from "../format";
import { useApp, useLoader } from "../state";

function hashId(): string {
  const m = window.location.hash.match(/^#\/results\/([^/?]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

function StatusBadge({ s }: { s: string }) {
  return (
    <Badge tone={s === "ok" ? "ok" : "warn"} testid="gen-status">
      <span data-status={s}>{s === "ok" ? "ok" : "warn"}</span>
    </Badge>
  );
}

function Detail({ gid, onChanged, onDeleted }: { gid: string; onChanged: (g: Generation) => void; onDeleted: (id: string) => void }) {
  const { catalog, requestTtsLoad } = useApp();
  const id = useId();
  const [g, setG] = useState<Generation | null>(null);
  const [err, setErr] = useState("");
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => {
    let stop = false;
    setG(null);
    setErr("");
    setMsg("");
    api
      .get<Generation>(`/api/generations/${gid}`)
      .then((r) => {
        if (stop) return;
        setG(r);
        setName(r.name);
      })
      .catch((e) => !stop && setErr(errText(e)));
    return () => {
      stop = true;
    };
  }, [gid]);
  if (err) return <ErrorAlert message={err} testid="gen-detail-error" />;
  if (!g)
    return (
      <p role="status" aria-busy="true">
        결과를 불러오는 중…
      </p>
    );
  const hid = `${id}-h`;
  return (
    <section className="card" aria-labelledby={hid} data-testid="gen-detail" data-gen-id={g.id}>
      <div className="row wrap gap">
        <h2 id={hid}>결과 상세: {g.name}</h2>
        <StatusBadge s={g.status} />
        <CommercialBadge value={g.commercial} license={g.license} />
      </div>
      <div className="row wrap gap">
        <audio controls preload="none" src={`/api/generations/${g.id}/audio`} aria-label={`결과 재생: ${g.name}`} data-testid="gen-detail-audio" />
        <a href={`/api/generations/${g.id}/audio`} download>
          내려받기
        </a>
        <button type="button" className="primary" onClick={() => requestTtsLoad(g)}>
          불러오기
        </button>
        <ConfirmButton
          label="결과 삭제"
          onConfirm={async () => {
            try {
              await api.del(`/api/generations/${g.id}`);
              onDeleted(g.id);
            } catch (e) {
              setErr(errText(e));
            }
          }}
        />
      </div>
      <form
        className="row wrap gap"
        aria-label="결과 이름 바꾸기"
        data-testid="gen-rename-form"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            const r = await api.patch<Generation>(`/api/generations/${g.id}`, { name });
            setG(r);
            onChanged(r);
            setMsg("이름을 바꿨습니다");
          } catch (ex) {
            setErr(errText(ex));
          }
        }}
      >
        <div className="field grow">
          <label htmlFor={`${id}-name`}>결과 이름</label>
          <input id={`${id}-name`} value={name} onChange={(e) => setName(e.target.value)} data-testid="gen-rename-input" />
        </div>
        <button type="submit" disabled={!name.trim() || name === g.name}>
          이름 저장
        </button>
      </form>
      {msg ? (
        <p role="status" className="success small">
          {msg}
        </p>
      ) : null}

      <dl className="meta">
        <div>
          <dt>엔진</dt>
          <dd>{g.engine_label}</dd>
        </div>
        <div>
          <dt>모델</dt>
          <dd>
            {g.model_label} <span className="mono small">({g.model?.id})</span>
          </dd>
        </div>
        <div>
          <dt>언어</dt>
          <dd>{langName((catalog?.languages ?? {}), g.language)}</dd>
        </div>
        <div>
          <dt>시드</dt>
          <dd className="mono" data-testid="gen-seed">
            {g.seed}
          </dd>
        </div>
        <div>
          <dt>길이</dt>
          <dd className="mono">{g.output?.duration?.toFixed(2)} s</dd>
        </div>
        <div>
          <dt>장치</dt>
          <dd>{(g.device ?? []).map((d) => (d.index !== undefined ? `GPU${d.index} ${d.name}` : d.name)).join(", ") || "—"}</dd>
        </div>
        <div>
          <dt>서비스</dt>
          <dd className="mono">
            {g.service?.version} {g.service?.git}
            {g.service?.dirty ? " (dirty)" : ""}
          </dd>
        </div>
        <div>
          <dt>만든 시각</dt>
          <dd>{fmtTime(g.created)}</dd>
        </div>
      </dl>

      <h3>대본</h3>
      <pre className="quote pre" data-testid="gen-text">
        {g.text}
      </pre>
      {g.text_used !== g.text ? (
        <details>
          <summary>엔진에 넘긴 글 (정규화 후)</summary>
          <pre className="quote pre">{g.text_used}</pre>
        </details>
      ) : null}

      <h3>참고 사본</h3>
      <div className="row wrap gap">
        <audio controls preload="none" src={`/api/generations/${g.id}/audio?which=ref`} aria-label="그때 쓴 참고 사본 재생" data-testid="gen-ref-audio" />
        <span>
          {String(g.ref?.name ?? "")} · {langName((catalog?.languages ?? {}), g.ref?.language)} · rev {g.ref?.rev}
          {g.ref?.from_generation ? ` · 결과 ${g.ref.from_generation}의 사본` : ""}
          {g.ref?.consent ? ` · 동의: ${CONSENT[g.ref.consent.basis] ?? g.ref.consent.basis}` : ""}
        </span>
      </div>
      <p className="quote small" data-testid="gen-ref-text">
        {g.ref?.text}
      </p>
      <p className="mono small muted">clip_sha256 {g.ref?.clip_sha256}</p>

      <h3>문단별 검사</h3>
      <div className="table-wrap">
        <table aria-label="문단별 검사 결과" data-testid="gen-parts-table">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">글</th>
              <th scope="col">시드</th>
              <th scope="col">길이</th>
              <th scope="col">시도</th>
              <th scope="col">basic</th>
              <th scope="col">lead_low_s</th>
              <th scope="col">match</th>
              <th scope="col">듣기</th>
            </tr>
          </thead>
          <tbody>
            {g.parts.map((p) => (
              <tr key={p.i} data-testid="gen-part-row" data-part={p.i} data-failed={!!p.checks?.failed}>
                <th scope="row">{p.i + 1}</th>
                <td className="small">
                  {p.text}
                  {p.checks?.heard ? <div className="muted">들린 글: {p.checks.heard}</div> : null}
                  {p.checks?.failed ? <Badge tone="bad">불량(다시 뽑기 소진)</Badge> : null}
                </td>
                <td className="mono">
                  {p.seed}
                  {p.seed_used !== undefined && p.seed_used !== p.seed ? ` (${p.seed_used})` : ""}
                </td>
                <td className="mono">{p.dur !== undefined ? `${p.dur.toFixed(2)}s` : "—"}</td>
                <td className="num">{p.attempts}</td>
                <td>{p.checks?.basic ?? "—"}</td>
                <td className="mono">{p.checks?.lead_low_s !== undefined ? p.checks.lead_low_s.toFixed(2) : "—"}</td>
                <td className="mono">{p.checks?.match !== undefined ? p.checks.match.toFixed(3) : "—"}</td>
                <td>
                  <audio controls preload="none" src={`/api/generations/${g.id}/audio?part=${p.i}`} aria-label={`문단 ${p.i + 1} 재생`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="two-col">
        <div>
          <h3>파라미터 (기본값까지 채운 실제 값)</h3>
          <KeyValue data={g.params} label="파라미터" testid="gen-params" />
        </div>
        <div>
          <h3>모델 지문</h3>
          <KeyValue data={Object.fromEntries(Object.entries(g.model ?? {}).filter(([k]) => k !== "files"))} label="모델 지문" testid="gen-model-fingerprint" />
          {g.aux_models?.length ? (
            <>
              <h3>보조 모델</h3>
              {g.aux_models.map((a, i) => (
                <KeyValue key={i} data={Object.fromEntries(Object.entries(a).filter(([k]) => k !== "files"))} label={`보조 모델 ${i + 1}`} />
              ))}
            </>
          ) : null}
          <h3>환경 판</h3>
          <KeyValue data={g.env} label="환경 판" testid="gen-env" />
          <h3>시간</h3>
          <KeyValue data={g.timings} label="시간" />
          <h3>출력</h3>
          <KeyValue data={g.output} label="출력" />
        </div>
      </div>
    </section>
  );
}

export function ResultsPage() {
  const { catalog } = useApp();
  const { data: gens, setData, error, loading, reload } = useLoader<Generation[]>("/api/generations", []);
  const [sel, setSel] = useState(hashId);
  useEffect(() => {
    const on = () => setSel(hashId());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const open = (gid: string) => {
    window.location.hash = `#/results/${gid}`;
  };
  return (
    <div className="stack">
      <section className="card" aria-labelledby="gens-h" data-testid="gen-list-section">
        <div className="row wrap gap">
          <h2 id="gens-h">생성 결과</h2>
          <button type="button" onClick={() => void reload()}>
            목록 새로 고침
          </button>
          {loading ? <span role="status">불러오는 중…</span> : null}
        </div>
        <ErrorAlert message={error} />
        {!loading && !gens.length ? (
          <p className="empty" data-testid="gen-list-empty">
            아직 생성 결과가 없습니다. TTS 화면에서 생성하세요.
          </p>
        ) : null}
        {gens.length ? (
          <div className="table-wrap">
            <table aria-label="생성 결과 목록" data-testid="gen-table">
              <thead>
                <tr>
                  <th scope="col">이름</th>
                  <th scope="col">엔진</th>
                  <th scope="col">모델</th>
                  <th scope="col">언어</th>
                  <th scope="col">길이</th>
                  <th scope="col">상태</th>
                  <th scope="col">만든 시각</th>
                  <th scope="col">재생</th>
                  <th scope="col">동작</th>
                </tr>
              </thead>
              <tbody>
                {gens.map((g) => (
                  <tr key={g.id} data-testid="gen-row" data-gen-id={g.id} aria-selected={sel === g.id}>
                    <th scope="row">
                      {g.name}
                      <div className="mono small muted">{g.id}</div>
                    </th>
                    <td>{g.engine_label}</td>
                    <td>{g.model_label}</td>
                    <td>{langName((catalog?.languages ?? {}), g.language)}</td>
                    <td className="mono">{fmtSec(g.output?.duration)}</td>
                    <td>
                      <StatusBadge s={g.status} />
                    </td>
                    <td className="small">{fmtTime(g.created)}</td>
                    <td>
                      <audio controls preload="none" src={`/api/generations/${g.id}/audio`} aria-label={`재생: ${g.name}`} />
                    </td>
                    <td>
                      <div className="row gap wrap">
                        <button type="button" onClick={() => open(g.id)} aria-pressed={sel === g.id}>
                          상세
                        </button>
                        <a href={`/api/generations/${g.id}/audio`} download>
                          내려받기
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
      {sel ? (
        <Detail
          gid={sel}
          onChanged={(ng) => setData((list) => list.map((x) => (x.id === ng.id ? { ...x, name: ng.name } : x)))}
          onDeleted={(gid) => {
            setData((list) => list.filter((x) => x.id !== gid));
            window.location.hash = "#/results";
          }}
        />
      ) : null}
    </div>
  );
}
