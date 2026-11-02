import { useEffect, useId, useMemo, useRef, useState } from "react";
import { api, errText, paramDefaults } from "../api";
import type { Catalog, Job, Params, Segment, Transcript } from "../api";
import { Badge, cleanParams, ConfirmButton, ErrorAlert, JobPanel, KeyValue, ModelSelect, ParamFields, UploadPicker } from "../components/ui";
import { fmtSec, fmtTime, langName } from "../format";
import { useApp, useLoader } from "../state";

function firstAsr(cat: Catalog): string {
  const d = cat.defaults.asr_model;
  if (cat.models[d]?.kind === "asr") return d;
  return Object.values(cat.models).find((m) => m.kind === "asr")?.id ?? "";
}

function TranscriptViewer({ tid, onSaved }: { tid: string; onSaved: () => void }) {
  const { catalog } = useApp();
  const id = useId();
  const [t, setT] = useState<Transcript | null>(null);
  const [segs, setSegs] = useState<Segment[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [cur, setCur] = useState(0);
  const [maxChars, setMaxChars] = useState(0);
  const audioRef = useRef<HTMLAudioElement>(null);
  const listRef = useRef<HTMLOListElement>(null);

  useEffect(() => {
    let stop = false;
    setT(null);
    setErr("");
    setMsg("");
    api
      .get<Transcript>(`/api/transcripts/${tid}`)
      .then((r) => {
        if (stop) return;
        setT(r);
        setSegs(r.segments.map((s) => ({ ...s })));
      })
      .catch((e) => !stop && setErr(errText(e)));
    return () => {
      stop = true;
    };
  }, [tid]);

  const active = useMemo(() => segs.findIndex((s) => cur >= s.start && cur < s.end), [segs, cur]);
  const total = useMemo(() => Math.max(t?.upload?.duration ?? 0, ...segs.map((s) => s.end), 0.001), [t, segs]);

  // 재생 위치의 구간이 보이게 스크롤(목록 안에서만)
  useEffect(() => {
    if (active < 0 || !listRef.current) return;
    const el = listRef.current.querySelector<HTMLElement>(`[data-index="${active}"]`);
    if (el && listRef.current) {
      const box = listRef.current;
      if (el.offsetTop < box.scrollTop || el.offsetTop + el.offsetHeight > box.scrollTop + box.clientHeight) box.scrollTop = el.offsetTop - box.clientHeight / 3;
    }
  }, [active]);

  if (err) return <ErrorAlert message={err} testid="asr-viewer-error" />;
  if (!t)
    return (
      <p role="status" aria-busy="true">
        전사 결과를 불러오는 중…
      </p>
    );

  const dirty = segs.some((s, i) => s.text !== t.segments[i]?.text);
  const seek = (sec: number, play = true) => {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = sec;
    setCur(sec);
    if (play) void a.play().catch(() => undefined);
  };
  const save = async () => {
    setErr("");
    setMsg("");
    try {
      // 글을 고친 구간은 단어 시각을 버린다 — 내보내기(max_chars)가 옛 단어로 자막을 만들지 않게
      const body = segs.map((s, i) => {
        if (s.text !== t.segments[i]?.text) {
          const { words: _w, ...rest } = s;
          void _w;
          return rest;
        }
        return s;
      });
      const r = await api.patch<Transcript>(`/api/transcripts/${t.id}`, { segments: body });
      setT(r);
      setSegs(r.segments.map((s) => ({ ...s })));
      setMsg("구간 수정을 저장했습니다");
      onSaved();
    } catch (e) {
      setErr(errText(e));
    }
  };
  const hid = `${id}-h`;
  const ex = (fmt: string) => `/api/transcripts/${t.id}/export?fmt=${fmt}&max_chars=${maxChars || 0}`;

  return (
    <section className="card" aria-labelledby={hid} data-testid="asr-viewer" data-transcript-id={t.id}>
      <div className="row wrap gap">
        <h2 id={hid}>전사 결과: {t.name}</h2>
        <Badge tone="info">{langName(catalog!.languages, t.language)}</Badge>
        {t.edited ? <Badge tone="muted">사람이 고침</Badge> : null}
        <span className="small muted">
          {t.model_label} · 구간 {segs.length}개 · {fmtTime(t.created)}
        </span>
      </div>
      <audio
        ref={audioRef}
        controls
        preload="auto"
        src={`/api/uploads/${t.upload.id}/audio`}
        aria-label={`전사 원본 재생: ${t.upload.name}`}
        data-testid="asr-audio"
        onTimeUpdate={(e) => setCur(e.currentTarget.currentTime)}
        onSeeked={(e) => setCur(e.currentTarget.currentTime)}
      />
      <p className="small mono" role="status" data-testid="asr-current-time" data-active-index={active}>
        재생 위치 {fmtSec(cur, 2)} / {fmtSec(total, 2)}
        {active >= 0 ? ` · 구간 ${active + 1}` : ""}
      </p>
      {/* 시각화용 막대 — 같은 동작을 아래 구간 목록 버튼이 접근 가능하게 제공한다 */}
      <div
        className="timeline"
        data-testid="asr-timeline"
        aria-hidden="true"
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          seek(((e.clientX - r.left) / r.width) * total);
        }}
      >
        {segs.map((s, i) => (
          <div
            key={i}
            className={`tl-seg ${i === active ? "on" : ""}`}
            data-testid="asr-timeline-seg"
            data-index={i}
            data-active={i === active}
            style={{ left: `${(s.start / total) * 100}%`, width: `${Math.max(0.3, ((s.end - s.start) / total) * 100)}%` }}
            title={`${fmtSec(s.start, 2)}–${fmtSec(s.end, 2)} ${s.text}`}
            onClick={(e) => {
              e.stopPropagation();
              seek(s.start);
            }}
          />
        ))}
        <div className="tl-head" style={{ left: `${(cur / total) * 100}%` }} />
      </div>
      <ol className="segments" ref={listRef} data-testid="asr-segments" aria-label="전사 구간">
        {segs.map((s, i) => (
          <li key={i} data-testid="asr-segment" data-index={i} data-active={i === active} aria-current={i === active ? "true" : undefined} className={i === active ? "on" : ""}>
            <button type="button" className="seg-time mono" onClick={() => seek(s.start)} aria-label={`구간 ${i + 1} 재생 ${fmtSec(s.start, 2)}부터`}>
              {fmtSec(s.start, 2)} – {fmtSec(s.end, 2)}
            </button>
            <label className="sr-only" htmlFor={`${id}-seg-${i}`}>
              구간 {i + 1} 글
            </label>
            <textarea
              id={`${id}-seg-${i}`}
              rows={Math.min(4, Math.max(1, Math.ceil(s.text.length / 60)))}
              value={s.text}
              data-testid="asr-segment-text"
              onChange={(e) => setSegs((list) => list.map((x, k) => (k === i ? { ...x, text: e.target.value } : x)))}
              onFocus={() => {
                if (audioRef.current?.paused) seek(s.start, false);
              }}
            />
          </li>
        ))}
      </ol>
      {!segs.length ? <p className="empty">구간이 없습니다(말소리를 찾지 못함).</p> : null}
      <div className="row wrap gap">
        <button type="button" className="primary" disabled={!dirty} onClick={() => void save()}>
          구간 수정 저장
        </button>
        {dirty ? <span className="small warn-text">저장하지 않은 수정이 있습니다. 글을 고친 구간은 단어 시각을 버립니다.</span> : null}
      </div>
      {msg ? (
        <p role="status" className="success small" data-testid="asr-save-status">
          {msg}
        </p>
      ) : null}
      <fieldset className="row wrap gap" data-testid="asr-export">
        <legend>내보내기</legend>
        <div className="field">
          <label htmlFor={`${id}-mc`}>자막 한 줄 최대 글자 (0 = 나누지 않음)</label>
          <input id={`${id}-mc`} type="number" min={0} max={200} value={maxChars} onChange={(e) => setMaxChars(Math.max(0, Number(e.target.value) || 0))} data-testid="asr-max-chars" />
        </div>
        {["srt", "vtt", "txt", "json"].map((f) => (
          <a key={f} href={ex(f)} download className="button-link" data-testid={`asr-export-${f}`}>
            {f.toUpperCase()} 내려받기
          </a>
        ))}
        {dirty ? <span className="small muted">내보내기는 저장된 내용 기준입니다.</span> : null}
      </fieldset>
      <details>
        <summary>전사 기록 (모델·파라미터·장치)</summary>
        <div className="two-col">
          <div>
            <h3>파라미터</h3>
            <KeyValue data={t.params} label="전사 파라미터" />
          </div>
          <div>
            <h3>모델</h3>
            <KeyValue data={Object.fromEntries(Object.entries(t.model ?? {}).filter(([k]) => k !== "files"))} label="전사 모델 지문" />
            <h3>장치·시간</h3>
            <KeyValue data={{ device: (t.device ?? []).map((d) => d.name).join(", "), ...t.timings }} label="장치와 시간" />
          </div>
        </div>
      </details>
    </section>
  );
}

export function AsrPage() {
  const { catalog } = useApp();
  const cat = catalog!;
  const id = useId();
  const [uploadId, setUploadId] = useState("");
  const [model, setModel] = useState(() => firstAsr(cat));
  const engine = cat.engines[cat.models[model]?.engine ?? ""];
  const specs = useMemo(() => (engine ? [...engine.common, ...engine.params] : []), [engine]);
  const [params, setParams] = useState<Params>(() => paramDefaults(specs));
  const [language, setLanguage] = useState("auto");
  const [name, setName] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [openTid, setOpenTid] = useState("");
  const { data: list, setData, error: listErr, loading, reload } = useLoader<Transcript[]>("/api/transcripts", []);

  const changeModel = (mid: string) => {
    setModel(mid);
    const e = cat.engines[cat.models[mid]?.engine ?? ""];
    if (!e) return;
    setParams(paramDefaults([...e.common, ...e.params]));
    if (language !== "auto" && !e.languages.includes(language)) setLanguage("auto");
  };

  const mm = cat.models[model];
  const env = engine ? cat.envs[engine.env] : undefined;
  const blockers: string[] = [];
  if (!uploadId) blockers.push("음성 파일을 올리거나 고르세요");
  if (!mm) blockers.push("ASR 모델을 고르세요");

  const submit = async () => {
    setErr("");
    try {
      const p = cleanParams(specs, { ...params, language });
      const j = await api.post<Job>("/api/asr", { model, upload_id: uploadId, language, params: p, name: name.trim() });
      setJobId(j.id);
    } catch (e) {
      setErr(errText(e));
    }
  };

  return (
    <div className="stack">
      <div className="two-col">
        <section className="card" aria-labelledby={`${id}-run`} data-testid="asr-form-section">
          <h2 id={`${id}-run`}>전사 실행</h2>
          <form
            aria-labelledby={`${id}-run`}
            data-testid="asr-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!blockers.length) void submit();
            }}
          >
            <UploadPicker value={uploadId} onChange={(v) => setUploadId(v)} testid="asr-upload" legend="받아 적을 음성" />
            <ModelSelect catalog={cat} kind="asr" value={model} onChange={changeModel} label="ASR 모델" testid="asr-model" />
            {mm ? (
              <div className="row wrap gap small">
                {!mm.check.ok ? <Badge tone="warn">모델 파일 미준비 — 모델 관리에서 받거나 위치를 지정하세요</Badge> : null}
                {env && !env.installed ? <Badge tone="warn">엔진 환경 미설치({engine?.env})</Badge> : null}
              </div>
            ) : null}
            {engine?.caveat ? <p className="caveat small">주의: {engine.caveat}</p> : null}
            <div className="grid-fields">
              <div className="field">
                <label htmlFor={`${id}-lang`}>언어</label>
                <select id={`${id}-lang`} value={language} onChange={(e) => setLanguage(e.target.value)} data-testid="asr-language">
                  <option value="auto">자동 감지</option>
                  {(engine?.languages ?? []).map((c) => (
                    <option key={c} value={c}>
                      {langName(cat.languages, c)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor={`${id}-name`}>전사 이름 (선택)</label>
                <input id={`${id}-name`} value={name} onChange={(e) => setName(e.target.value)} placeholder="비우면 파일 이름" data-testid="asr-name" />
              </div>
            </div>
            {engine ? <ParamFields specs={specs} values={params} onChange={(k, v) => setParams((p) => ({ ...p, [k]: v }))} exclude={["language"]} testid="asr-params" /> : null}
            {blockers.length ? (
              <ul className="blockers small" role="status" aria-label="실행 전에 필요한 것" data-testid="asr-blockers">
                {blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            ) : null}
            <button type="submit" className="primary" disabled={blockers.length > 0}>
              전사 실행
            </button>
            <ErrorAlert message={err} testid="asr-error" />
          </form>
          <JobPanel
            jobId={jobId}
            testid="asr-job"
            onDone={(j) => {
              void reload();
              const tid = (j.result as { transcript_id?: string } | null)?.transcript_id;
              if (j.status === "done" && tid) setOpenTid(tid);
            }}
          />
        </section>

        <section className="card" aria-labelledby={`${id}-list`} data-testid="transcript-list-section">
          <div className="row wrap gap">
            <h2 id={`${id}-list`}>저장된 전사</h2>
            <button type="button" onClick={() => void reload()}>
              목록 새로 고침
            </button>
            {loading ? <span role="status">불러오는 중…</span> : null}
          </div>
          <ErrorAlert message={listErr} />
          {!loading && !list.length ? (
            <p className="empty" data-testid="transcript-list-empty">
              아직 저장된 전사가 없습니다.
            </p>
          ) : null}
          {list.length ? (
            <div className="table-wrap">
              <table aria-label="저장된 전사 목록" data-testid="transcript-table">
                <thead>
                  <tr>
                    <th scope="col">이름</th>
                    <th scope="col">모델</th>
                    <th scope="col">언어</th>
                    <th scope="col">구간</th>
                    <th scope="col">만든 시각</th>
                    <th scope="col">동작</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((t) => (
                    <tr key={t.id} data-testid="transcript-row" data-transcript-id={t.id} aria-selected={openTid === t.id}>
                      <th scope="row">
                        {t.name}
                        {t.edited ? (
                          <>
                            {" "}
                            <Badge tone="muted">고침</Badge>
                          </>
                        ) : null}
                        <div className="mono small muted">{t.id}</div>
                      </th>
                      <td>{t.model_label}</td>
                      <td>{langName(cat.languages, t.language)}</td>
                      <td className="num">{t.segment_count ?? t.segments?.length ?? 0}</td>
                      <td className="small">{fmtTime(t.created)}</td>
                      <td>
                        <div className="row gap wrap">
                          <button type="button" onClick={() => setOpenTid(t.id)} aria-pressed={openTid === t.id}>
                            열기
                          </button>
                          <ConfirmButton
                            label="전사 삭제"
                            onConfirm={async () => {
                              try {
                                await api.del(`/api/transcripts/${t.id}`);
                                setData((l) => l.filter((x) => x.id !== t.id));
                                if (openTid === t.id) setOpenTid("");
                              } catch (e) {
                                setErr(errText(e));
                              }
                            }}
                          />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      </div>
      {openTid ? <TranscriptViewer key={openTid} tid={openTid} onSaved={() => void reload()} /> : null}
    </div>
  );
}
