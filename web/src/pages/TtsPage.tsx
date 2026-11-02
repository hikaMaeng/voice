import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { api, errText, paramDefaults } from "../api";
import type { Catalog, ConsentBasis, Generation, Job, Params, RefSet } from "../api";
import { Badge, cleanParams, CommercialBadge, ConfirmButton, ErrorAlert, JobPanel, ModelSelect, ParamFields, UploadPicker } from "../components/ui";
import { CONSENT, commercialInfo, fmtSec, fmtTime, langName } from "../format";
import { useApp } from "../state";

const TRANSCRIPT_HINT =
  "자동 전사문은 틀릴 수 있습니다. 목소리 복제 품질은 참고 전사문이 클립에서 실제로 한 말과 얼마나 정확히 맞는지에 크게 기댑니다 — 클립을 들어 보고 틀린 글자를 고쳐 주세요.";

function LangSelect({ catalog, codes, value, onChange, label, allowEmpty, testid, required }: { catalog: Catalog; codes: string[]; value: string; onChange: (v: string) => void; label: string; allowEmpty?: string; testid: string; required?: boolean }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} required={required} aria-required={required}>
        {allowEmpty !== undefined ? <option value="">{allowEmpty}</option> : null}
        {codes.map((c) => (
          <option key={c} value={c}>
            {langName(catalog.languages, c)}
          </option>
        ))}
      </select>
    </div>
  );
}

// ───────────────────────── 참조 세트 만들기 ─────────────────────────

function RefCreate({ onCreated }: { onCreated: (refId: string) => void }) {
  const { catalog } = useApp();
  const id = useId();
  const [uploadId, setUploadId] = useState("");
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"auto" | "manual">("auto");
  const [language, setLanguage] = useState("");
  const [text, setText] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [asrModel, setAsrModel] = useState(catalog!.defaults.asr_model);
  const [basis, setBasis] = useState<ConsentBasis | "">("");
  const [agreed, setAgreed] = useState(false);
  const [note, setNote] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [done, setDone] = useState("");
  const cat = catalog!;
  const asrOk = !!cat.models[asrModel] && cat.models[asrModel].kind === "asr";

  const blockers: string[] = [];
  if (!uploadId) blockers.push("음성 파일을 올리거나 고르세요");
  if (mode === "manual" && !language) blockers.push("직접 모드는 참고 언어를 골라야 합니다");
  if (mode === "manual" && !text.trim()) blockers.push("직접 모드는 참고 전사문을 넣어야 합니다");
  if (mode === "auto" && !asrOk) blockers.push("자동 전사에 쓸 ASR 모델을 고르세요");
  if ((start === "") !== (end === "")) blockers.push("구간은 시작과 끝을 함께 넣어야 합니다(둘 다 비우면 자동)");
  if (start !== "" && end !== "" && Number(end) - Number(start) < 1) blockers.push("구간은 1초 이상이어야 합니다");
  if (!basis) blockers.push("목소리 사용 동의 근거를 고르세요");
  if (!agreed) blockers.push("목소리 사용 권리 확인에 체크하세요");

  const submit = async () => {
    setErr("");
    setDone("");
    try {
      const j = await api.post<Job>("/api/refs", {
        upload_id: uploadId,
        name: name.trim(),
        mode,
        language,
        text: mode === "manual" ? text : "",
        start: start === "" ? null : Number(start),
        end: end === "" ? null : Number(end),
        asr_model: mode === "auto" ? asrModel : "",
        asr_params: {},
        consent: { basis, agreed, note: note.trim() },
      });
      setJobId(j.id);
    } catch (e) {
      setErr(errText(e));
    }
  };

  return (
    <section className="card" aria-labelledby={`${id}-h`} data-testid="ref-create">
      <h2 id={`${id}-h`}>참조 세트 만들기</h2>
      <form
        aria-labelledby={`${id}-h`}
        onSubmit={(e) => {
          e.preventDefault();
          if (!blockers.length) void submit();
        }}
      >
        <UploadPicker value={uploadId} onChange={(v) => setUploadId(v)} testid="ref-upload" legend="참고 음성" />
        <div className="grid-fields">
          <div className="field">
            <label htmlFor={`${id}-name`}>세트 이름</label>
            <input id={`${id}-name`} type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="비우면 파일 이름" data-testid="ref-name" />
          </div>
        </div>
        <fieldset data-testid="ref-mode">
          <legend>전사 방식</legend>
          <label className="inline">
            <input type="radio" name={`${id}-mode`} value="auto" checked={mode === "auto"} onChange={() => setMode("auto")} />
            자동 (ASR 로 언어·전사문)
          </label>
          <label className="inline">
            <input type="radio" name={`${id}-mode`} value="manual" checked={mode === "manual"} onChange={() => setMode("manual")} />
            직접 (언어 선택 + 전사문 입력)
          </label>
        </fieldset>
        <div className="grid-fields">
          {mode === "auto" ? <ModelSelect catalog={cat} kind="asr" value={asrModel} onChange={setAsrModel} label="자동 전사 ASR 모델" testid="ref-asr-model" /> : null}
          <LangSelect
            catalog={cat}
            codes={Object.keys(cat.languages)}
            value={language}
            onChange={setLanguage}
            label={mode === "auto" ? "참고 언어 (비우면 자동 감지)" : "참고 언어"}
            allowEmpty={mode === "auto" ? "자동 감지" : "— 고르세요 —"}
            testid="ref-language"
            required={mode === "manual"}
          />
          <div className="field">
            <label htmlFor={`${id}-start`}>시작 (초, 선택)</label>
            <input id={`${id}-start`} type="number" min={0} step={0.01} value={start} onChange={(e) => setStart(e.target.value)} data-testid="ref-start" aria-describedby={`${id}-range-help`} />
          </div>
          <div className="field">
            <label htmlFor={`${id}-end`}>끝 (초, 선택)</label>
            <input id={`${id}-end`} type="number" min={0} step={0.01} value={end} onChange={(e) => setEnd(e.target.value)} data-testid="ref-end" aria-describedby={`${id}-range-help`} />
          </div>
        </div>
        <small id={`${id}-range-help`} className="help">
          구간을 비우면 자동 모드는 8~15초 창을 스스로 고르고, 직접 모드는 앞뒤 무음만 걷어 냅니다.
        </small>
        {mode === "manual" ? (
          <div className="field">
            <label htmlFor={`${id}-text`}>참고 전사문</label>
            <textarea id={`${id}-text`} rows={3} value={text} onChange={(e) => setText(e.target.value)} required aria-required="true" data-testid="ref-text" aria-describedby={`${id}-text-help`} />
            <small id={`${id}-text-help`} className="help">
              클립에서 실제로 한 말을 그대로 적습니다. {TRANSCRIPT_HINT}
            </small>
          </div>
        ) : (
          <p className="help small">자동 전사문은 만든 뒤 아래 「저장된 참조 세트」에서 고칠 수 있습니다. {TRANSCRIPT_HINT}</p>
        )}
        <fieldset data-testid="ref-consent" className="consent">
          <legend>목소리 사용 동의</legend>
          <div className="grid-fields">
            <div className="field">
              <label htmlFor={`${id}-basis`}>동의 근거</label>
              <select id={`${id}-basis`} value={basis} onChange={(e) => setBasis(e.target.value as ConsentBasis | "")} required aria-required="true" data-testid="ref-consent-basis">
                <option value="">— 고르세요 —</option>
                {(Object.keys(CONSENT) as ConsentBasis[]).map((k) => (
                  <option key={k} value={k}>
                    {CONSENT[k]}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor={`${id}-note`}>동의 메모 (선택)</label>
              <input id={`${id}-note`} type="text" value={note} onChange={(e) => setNote(e.target.value)} data-testid="ref-consent-note" />
            </div>
          </div>
          <div className="field field-check">
            <input id={`${id}-agree`} type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} data-testid="ref-consent-agree" />
            <label htmlFor={`${id}-agree`}>이 목소리를 위 근거에 따라 복제에 쓸 권리가 있음을 확인합니다</label>
          </div>
        </fieldset>
        {blockers.length ? (
          <ul className="blockers small" role="status" aria-label="만들기 전에 필요한 것" data-testid="ref-create-blockers">
            {blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        ) : null}
        <button type="submit" className="primary" disabled={blockers.length > 0}>
          참조 세트 만들기
        </button>
        <ErrorAlert message={err} testid="ref-create-error" />
      </form>
      <JobPanel
        jobId={jobId}
        testid="ref-job"
        onDone={(j) => {
          if (j.status === "done" && j.result) {
            const r = j.result as { ref_id: string; text: string; language: string };
            setDone(`참조 세트를 만들었습니다 (${langName(cat.languages, r.language)}): 「${r.text}」 — 아래 목록에서 들어 보고 전사문을 고치세요.`);
            onCreated(r.ref_id);
          }
        }}
      />
      {done ? (
        <p role="status" className="success" data-testid="ref-create-done">
          {done}
        </p>
      ) : null}
    </section>
  );
}

// ───────────────────────── 저장된 참조 세트 ─────────────────────────

function RefItem({ r, onChanged, onDeleted, onUse, selected }: { r: RefSet; onChanged: (r: RefSet) => void; onDeleted: (id: string) => void; onUse: (id: string) => void; selected: boolean }) {
  const { catalog } = useApp();
  const id = useId();
  const [name, setName] = useState(r.name);
  const [language, setLanguage] = useState(r.language);
  const [text, setText] = useState(r.text);
  const [rs, setRs] = useState(String(r.window?.[0] ?? ""));
  const [re, setRe] = useState(String(r.window?.[1] ?? ""));
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setName(r.name);
    setLanguage(r.language);
    setText(r.text);
    setRs(String(r.window?.[0] ?? ""));
    setRe(String(r.window?.[1] ?? ""));
  }, [r.rev, r.name, r.language, r.text, r.window]);
  const dirty = name !== r.name || language !== r.language || text !== r.text;
  const hid = `${id}-h`;
  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      await fn();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <li data-testid="ref-item" data-ref-id={r.id} data-selected={selected}>
      <article className="card inner" aria-labelledby={hid}>
        <div className="row wrap gap">
          <h3 id={hid}>{r.name}</h3>
          <Badge tone="muted">{r.mode === "auto" ? "자동 전사" : "직접 입력"}</Badge>
          <Badge tone="info">동의: {CONSENT[r.consent?.basis] ?? r.consent?.basis}</Badge>
          {selected ? <Badge tone="ok">생성에 선택됨</Badge> : null}
        </div>
        <dl className="meta">
          <div>
            <dt>언어</dt>
            <dd data-testid="ref-language-value">{langName(catalog!.languages, r.language)}</dd>
          </div>
          <div>
            <dt>구간</dt>
            <dd className="mono">
              {fmtSec(r.window?.[0], 2)} – {fmtSec(r.window?.[1], 2)} ({r.picked})
            </dd>
          </div>
          <div>
            <dt>클립 길이</dt>
            <dd className="mono">{r.clip_duration?.toFixed(2)} s</dd>
          </div>
          <div>
            <dt>f0 중앙값</dt>
            <dd className="mono">{r.f0_median ? `${r.f0_median.toFixed(1)} Hz` : "—"}</dd>
          </div>
          <div>
            <dt>원본</dt>
            <dd>
              {r.upload?.name} ({fmtSec(r.upload?.duration)})
            </dd>
          </div>
          <div>
            <dt>동의</dt>
            <dd>
              {CONSENT[r.consent?.basis] ?? r.consent?.basis}
              {r.consent?.agreed_at ? ` · ${r.consent.agreed_at}` : ""}
              {r.consent?.note ? ` · ${r.consent.note}` : ""}
            </dd>
          </div>
          <div>
            <dt>판</dt>
            <dd className="mono">rev {r.rev}</dd>
          </div>
          <div>
            <dt>만든 시각</dt>
            <dd>{fmtTime(r.created)}</dd>
          </div>
        </dl>
        <p className="quote" data-testid="ref-text-value">
          {r.text}
        </p>
        <div className="row wrap gap">
          <label className="audio-label">
            <span>잘린 클립</span>
            <audio controls preload="none" src={`/api/refs/${r.id}/audio?which=clip&rev=${r.rev}`} aria-label={`참고 클립 재생: ${r.name}`} data-testid="ref-clip-audio" />
          </label>
          <label className="audio-label">
            <span>원본</span>
            <audio controls preload="none" src={`/api/refs/${r.id}/audio?which=source`} aria-label={`원본 재생: ${r.name}`} data-testid="ref-source-audio" />
          </label>
        </div>
        <details>
          <summary>전사문·이름 고치기 / 구간 다시 자르기</summary>
          <form
            aria-label={`${r.name} 고치기`}
            data-testid="ref-edit-form"
            onSubmit={(e) => {
              e.preventDefault();
              void act(async () => {
                const nr = await api.patch<RefSet>(`/api/refs/${r.id}`, { name, language, text });
                onChanged(nr);
                setMsg("저장했습니다");
              });
            }}
          >
            <div className="grid-fields">
              <div className="field">
                <label htmlFor={`${id}-name`}>세트 이름</label>
                <input id={`${id}-name`} value={name} onChange={(e) => setName(e.target.value)} data-testid="ref-edit-name" />
              </div>
              <LangSelect catalog={catalog!} codes={Object.keys(catalog!.languages)} value={language} onChange={setLanguage} label="언어" testid="ref-edit-language" />
            </div>
            <div className="field">
              <label htmlFor={`${id}-text`}>전사문</label>
              <textarea id={`${id}-text`} rows={3} value={text} onChange={(e) => setText(e.target.value)} data-testid="ref-edit-text" aria-describedby={`${id}-hint`} />
              <small id={`${id}-hint`} className="help">
                {TRANSCRIPT_HINT}
              </small>
              {r.auto_text && r.auto_text !== r.text ? <small className="help">ASR 원문: 「{r.auto_text}」</small> : null}
            </div>
            <button type="submit" className="primary" disabled={!dirty || busy}>
              세트 저장
            </button>
          </form>
          <form
            aria-label={`${r.name} 구간 다시 자르기`}
            data-testid="ref-recut-form"
            onSubmit={(e) => {
              e.preventDefault();
              void act(async () => {
                const nr = await api.post<RefSet>(`/api/refs/${r.id}/recut`, { start: Number(rs), end: Number(re) });
                onChanged(nr);
                setMsg(`구간을 다시 잘랐습니다: ${fmtSec(nr.window[0], 2)} – ${fmtSec(nr.window[1], 2)}`);
              });
            }}
          >
            <div className="grid-fields">
              <div className="field">
                <label htmlFor={`${id}-rs`}>새 시작 (초)</label>
                <input id={`${id}-rs`} type="number" min={0} step={0.01} value={rs} onChange={(e) => setRs(e.target.value)} data-testid="ref-recut-start" />
              </div>
              <div className="field">
                <label htmlFor={`${id}-re`}>새 끝 (초)</label>
                <input id={`${id}-re`} type="number" min={0} step={0.01} value={re} onChange={(e) => setRe(e.target.value)} data-testid="ref-recut-end" />
              </div>
            </div>
            <small className="help">원본 길이 {fmtSec(r.upload?.duration)}. 다시 자르면 전사문은 그 구간의 자동 전사로 바뀝니다(있을 때) — 다시 확인하세요.</small>
            <div>
              <button type="submit" disabled={busy || rs === "" || re === ""}>
                구간 다시 자르기
              </button>
            </div>
          </form>
        </details>
        <div className="row wrap gap">
          <button type="button" onClick={() => onUse(r.id)} disabled={selected}>
            이 세트로 생성
          </button>
          <ConfirmButton
            label="세트 삭제"
            onConfirm={() =>
              act(async () => {
                await api.del(`/api/refs/${r.id}`);
                onDeleted(r.id);
              })
            }
          />
        </div>
        {msg ? (
          <p role="status" className="success small">
            {msg}
          </p>
        ) : null}
        <ErrorAlert message={err} />
      </article>
    </li>
  );
}

// ───────────────────────── 생성 폼 ─────────────────────────

interface LoadedInfo {
  genId: string;
  genName: string;
  refMode: "set" | "copy";
  refName: string;
  textOverridden: boolean;
  missingModel: boolean;
}

function firstTts(cat: Catalog): string {
  const d = cat.defaults.tts_model;
  if (cat.models[d]?.kind === "tts") return d;
  return Object.values(cat.models).find((m) => m.kind === "tts")?.id ?? "";
}

export function TtsPage() {
  const { catalog, ttsLoad, consumeTtsLoad } = useApp();
  const cat = catalog!;
  const id = useId();
  const [refs, setRefs] = useState<RefSet[]>([]);
  const [refsLoaded, setRefsLoaded] = useState(false);
  const [refsErr, setRefsErr] = useState("");

  const [model, setModel] = useState(() => firstTts(cat));
  const engine = cat.engines[cat.models[model]?.engine ?? ""];
  const specs = useMemo(() => (engine ? [...engine.common, ...engine.params] : []), [engine]);
  const [params, setParams] = useState<Params>(() => paramDefaults(specs));
  const [language, setLanguage] = useState(() => (engine?.languages.includes("ko") ? "ko" : engine?.languages[0] ?? "ko"));
  const [text, setText] = useState("");
  const [refChoice, setRefChoice] = useState("");
  const [refText, setRefText] = useState("");
  const [name, setName] = useState("");
  const [loaded, setLoaded] = useState<LoadedInfo | null>(null);
  const [copyGen, setCopyGen] = useState<Generation | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [resultGen, setResultGen] = useState<TtsDone | null>(null);
  const [err, setErr] = useState("");

  const loadRefs = useCallback(async () => {
    try {
      const list = await api.get<RefSet[]>("/api/refs");
      setRefs(list);
      setRefsErr("");
      return list;
    } catch (e) {
      setRefsErr(errText(e));
      return [];
    } finally {
      setRefsLoaded(true);
    }
  }, []);
  useEffect(() => {
    void loadRefs();
  }, [loadRefs]);

  // 처음 들어왔을 때 참조 세트가 하나라도 있으면 가장 최근 것을 고른다
  useEffect(() => {
    if (refsLoaded && !refChoice && refs.length && !ttsLoad) setRefChoice(`ref:${refs[0].id}`);
  }, [refsLoaded, refs, refChoice, ttsLoad]);

  const changeModel = (mid: string) => {
    const m = cat.models[mid];
    const e = m ? cat.engines[m.engine] : undefined;
    setModel(mid);
    if (!e) return;
    const commonKeys = new Set(e.common.map((p) => p.key));
    const next = paramDefaults([...e.common, ...e.params]);
    for (const k of Object.keys(params)) if (commonKeys.has(k)) next[k] = params[k];
    setParams(next);
    if (!e.languages.includes(language)) setLanguage(e.languages.includes("ko") ? "ko" : e.languages[0]);
  };

  // 결과물 「불러오기」: 생성 당시 값으로 폼을 채운다
  useEffect(() => {
    if (!ttsLoad || !refsLoaded) return;
    const g = ttsLoad.generation;
    const mid = g.model?.id;
    const m = cat.models[mid];
    const e = m ? cat.engines[m.engine] : undefined;
    if (m && e) {
      setModel(mid);
      setParams({ ...paramDefaults([...e.common, ...e.params]), ...g.params });
    } else {
      setParams({ ...g.params });
    }
    setLanguage(g.language);
    setText(g.text);
    setName("");
    const same = g.ref?.id ? refs.find((r) => r.id === g.ref.id && r.clip_sha256 === g.ref.clip_sha256 && r.language === g.ref.language) : undefined;
    let textOverridden = false;
    if (same) {
      setRefChoice(`ref:${same.id}`);
      textOverridden = !!g.ref.text && same.text !== g.ref.text;
      setRefText(textOverridden ? String(g.ref.text) : "");
      setCopyGen(null);
    } else {
      setRefChoice(`gen:${g.id}`);
      setRefText("");
      setCopyGen(g);
    }
    setLoaded({ genId: g.id, genName: g.name, refMode: same ? "set" : "copy", refName: String(g.ref?.name ?? ""), textOverridden, missingModel: !m });
    setResultGen(null);
    setJobId(null);
    consumeTtsLoad();
  }, [ttsLoad, refsLoaded, refs, cat, consumeTtsLoad]);

  const mm = cat.models[model];
  const env = engine ? cat.envs[engine.env] : undefined;
  const ci = mm ? commercialInfo(mm.commercial) : null;
  const refSel = refChoice.startsWith("ref:") ? refs.find((r) => `ref:${r.id}` === refChoice) : undefined;
  const refFromGen = refChoice.startsWith("gen:") ? refChoice.slice(4) : "";

  const blockers: string[] = [];
  if (!mm) blockers.push("TTS 모델을 고르세요");
  if (!text.trim()) blockers.push("대본을 넣으세요");
  if (!refSel && !refFromGen) blockers.push("참조 세트를 고르세요");

  const submit = async () => {
    setErr("");
    setResultGen(null);
    try {
      const body: Record<string, unknown> = {
        model,
        text,
        language,
        params: cleanParams(specs, params),
        name: name.trim(),
        ref_text: refText.trim(),
      };
      if (refSel) body.ref_id = refSel.id;
      else body.ref_from_generation = refFromGen;
      const j = await api.post<Job>("/api/tts", body);
      setJobId(j.id);
    } catch (e) {
      setErr(errText(e));
    }
  };

  const updateRef = (nr: RefSet) => setRefs((rs) => rs.map((r) => (r.id === nr.id ? nr : r)));

  return (
    <div className="stack">
      <div className="two-col">
        <div className="stack">
          <RefCreate
            onCreated={async (rid) => {
              await loadRefs();
              setRefChoice(`ref:${rid}`);
            }}
          />
          <section className="card" aria-labelledby={`${id}-refs`} data-testid="ref-list-section">
            <div className="row wrap gap">
              <h2 id={`${id}-refs`}>저장된 참조 세트</h2>
              <button type="button" onClick={() => void loadRefs()}>
                목록 새로 고침
              </button>
            </div>
            <ErrorAlert message={refsErr} />
            {refsLoaded && !refs.length ? (
              <p className="empty" data-testid="ref-list-empty">
                아직 참조 세트가 없습니다. 위에서 음성을 올려 만드세요.
              </p>
            ) : null}
            <ul className="plain stack" data-testid="ref-list" aria-label="참조 세트 목록">
              {refs.map((r) => (
                <RefItem
                  key={r.id}
                  r={r}
                  selected={refChoice === `ref:${r.id}`}
                  onChanged={updateRef}
                  onUse={(rid) => setRefChoice(`ref:${rid}`)}
                  onDeleted={(rid) => {
                    setRefs((rs) => rs.filter((x) => x.id !== rid));
                    if (refChoice === `ref:${rid}`) setRefChoice("");
                  }}
                />
              ))}
            </ul>
          </section>
        </div>

        <section className="card sticky" aria-labelledby={`${id}-gen`} data-testid="tts-form-section">
          <h2 id={`${id}-gen`}>생성</h2>
          {loaded ? (
            <div role="status" className="banner" data-testid="tts-loaded-banner" data-gen-id={loaded.genId} data-ref-mode={loaded.refMode}>
              <p>
                결과 「{loaded.genName}」(<span className="mono">{loaded.genId}</span>)의 생성 당시 값(모델·언어·대본·파라미터·시드)을 불러왔습니다.
              </p>
              {loaded.refMode === "set" ? (
                <p data-testid="tts-loaded-ref">참고: 저장된 세트 「{loaded.refName}」를 그대로 씁니다(클립 지문 일치).</p>
              ) : (
                <p data-testid="tts-loaded-ref">
                  참고: 원래 세트 「{loaded.refName}」가 지워졌거나 바뀌어 그 결과에 남은 <strong>참고 사본</strong>을 씁니다 (ref_from_generation=<span className="mono">{loaded.genId}</span>).
                </p>
              )}
              {loaded.textOverridden ? <p>세트 전사문이 그 뒤 바뀌어, 생성 당시 전사문을 이번 생성에만 씁니다.</p> : null}
              {loaded.missingModel ? <p className="warn-text">기록된 모델이 지금 목록에 없습니다(시험 엔진 숨김 설정 등). 모델을 다시 고르세요.</p> : null}
              <button type="button" onClick={() => setLoaded(null)}>
                안내 닫기
              </button>
            </div>
          ) : null}
          <form
            aria-labelledby={`${id}-gen`}
            data-testid="tts-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!blockers.length) void submit();
            }}
          >
            <ModelSelect catalog={cat} kind="tts" value={model} onChange={changeModel} label="TTS 모델" testid="tts-model" />
            {mm ? (
              <div className="row wrap gap small" data-testid="tts-model-info">
                <CommercialBadge value={mm.commercial} license={mm.license} />
                {ci && mm.commercial !== true ? (
                  <Badge tone={mm.commercial === false ? "bad" : "warn"} testid="tts-noncommercial-warning">
                    {mm.commercial === false ? "경고: 비상업 모델 — 상업적으로 쓸 수 없습니다" : mm.commercial === "limited" ? "주의: 조건부 상업 사용 — 라이선스 조건을 확인하세요" : "주의: 상업 사용 가능 여부 확인 필요"}
                  </Badge>
                ) : null}
                {!mm.check.ok ? (
                  <Badge tone="warn" testid="tts-model-not-ready">
                    모델 파일 미준비 — 모델 관리에서 받거나 위치를 지정하세요
                  </Badge>
                ) : null}
                {env && !env.installed ? (
                  <Badge tone="warn" testid="tts-env-not-installed">
                    엔진 환경 미설치({engine?.env})
                  </Badge>
                ) : null}
              </div>
            ) : null}
            {engine?.caveat ? <p className="caveat small">주의: {engine.caveat}</p> : null}
            <div className="grid-fields">
              <LangSelect catalog={cat} codes={engine?.languages ?? []} value={language} onChange={setLanguage} label="대본 언어" testid="tts-language" />
              <div className="field">
                <label htmlFor={`${id}-ref`}>참조 세트</label>
                <select id={`${id}-ref`} value={refChoice} onChange={(e) => setRefChoice(e.target.value)} data-testid="tts-ref">
                  <option value="">— 고르세요 —</option>
                  {copyGen ? <option value={`gen:${copyGen.id}`}>결과 「{copyGen.name}」의 참고 사본 ({String(copyGen.ref?.name ?? "")})</option> : null}
                  {refs.map((r) => (
                    <option key={r.id} value={`ref:${r.id}`}>
                      {r.name} · {r.language} · {r.clip_duration?.toFixed(1)}s
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {refSel ? (
              <p className="quote small" data-testid="tts-ref-preview">
                {refSel.text}
              </p>
            ) : null}
            {refFromGen && copyGen ? (
              <div className="row wrap gap">
                <p className="quote small grow" data-testid="tts-ref-preview">
                  {String(copyGen.ref?.text ?? "")}
                </p>
                <audio controls preload="none" src={`/api/generations/${copyGen.id}/audio?which=ref`} aria-label="참고 사본 재생" />
              </div>
            ) : null}
            <details open={!!refText}>
              <summary>이번 생성에만 쓸 참고 전사문 (선택)</summary>
              <div className="field">
                <label htmlFor={`${id}-reftext`}>참고 전사문 덮어쓰기</label>
                <textarea id={`${id}-reftext`} rows={2} value={refText} onChange={(e) => setRefText(e.target.value)} data-testid="tts-ref-text" />
                <small className="help">비우면 세트의 전사문을 씁니다. 세트 자체는 바뀌지 않습니다.</small>
              </div>
            </details>
            <div className="field">
              <label htmlFor={`${id}-text`}>대본</label>
              <textarea id={`${id}-text`} rows={8} value={text} onChange={(e) => setText(e.target.value)} data-testid="tts-text" aria-describedby={`${id}-text-help`} />
              <small id={`${id}-text-help`} className="help">
                빈 줄로 문단을 나눕니다. {text.trim() ? `문단 ${text.trim().split(/\n\s*\n/).length}개 · ${text.length}자` : ""}
              </small>
            </div>
            <div className="field">
              <label htmlFor={`${id}-name`}>결과 이름 (선택)</label>
              <input id={`${id}-name`} type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="비우면 대본 앞부분" data-testid="tts-name" />
            </div>
            {engine ? <ParamFields specs={specs} values={params} onChange={(k, v) => setParams((p) => ({ ...p, [k]: v }))} testid="tts-params" /> : null}
            {blockers.length ? (
              <ul className="blockers small" role="status" aria-label="생성 전에 필요한 것" data-testid="tts-blockers">
                {blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            ) : null}
            <button type="submit" className="primary" disabled={blockers.length > 0}>
              생성
            </button>
            <ErrorAlert message={err} testid="tts-error" />
          </form>
          <JobPanel
            jobId={jobId}
            testid="tts-job"
            onDone={(j) => {
              if (j.status === "done" && j.result) setResultGen(j.result as unknown as TtsDone);
            }}
          />
          {resultGen ? <TtsResult r={resultGen} /> : null}
        </section>
      </div>
    </div>
  );
}

interface TtsDone {
  generation_id: string;
  duration: number;
  status: string;
}

function TtsResult({ r }: { r: TtsDone }) {
  return (
    <section className="result-box" aria-label="생성 결과" data-testid="tts-result" data-gen-id={r.generation_id} data-status={r.status}>
      <div className="row wrap gap">
        <strong>생성 완료</strong>
        <Badge tone={r.status === "ok" ? "ok" : "warn"}>{r.status === "ok" ? "검사 통과" : "검사 경고"}</Badge>
        <span className="mono small">{r.duration?.toFixed(2)} s</span>
      </div>
      <audio controls src={`/api/generations/${r.generation_id}/audio`} aria-label="생성 결과 재생" data-testid="tts-result-audio" />
      <div className="row wrap gap">
        <a href={`/api/generations/${r.generation_id}/audio`} download>
          내려받기
        </a>
        <a href={`#/results/${r.generation_id}`}>결과물에서 자세히 보기</a>
      </div>
    </section>
  );
}
