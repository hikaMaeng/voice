import { useEffect, useId, useState } from "react";
import type { ReactNode } from "react";
import { api, errText } from "../api";
import type { Settings, SystemInfo } from "../api";
import { Badge, ConfirmButton, ErrorAlert } from "../components/ui";
import { useApp } from "../state";

type Draft = Omit<Settings, "model_paths">;

function Field({ label, help, children, id }: { label: string; help?: string; children: (id: string, helpId?: string) => ReactNode; id: string }) {
  const helpId = help ? `${id}-help` : undefined;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children(id, helpId)}
      {help ? (
        <small id={helpId} className="help">
          {help}
        </small>
      ) : null}
    </div>
  );
}

function Check({ id, label, checked, onChange, help, testid }: { id: string; label: string; checked: boolean; onChange: (v: boolean) => void; help?: string; testid: string }) {
  return (
    <div className="field field-check">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} data-testid={testid} aria-describedby={help ? `${id}-help` : undefined} />
      <label htmlFor={id}>{label}</label>
      {help ? (
        <small id={`${id}-help`} className="help">
          {help}
        </small>
      ) : null}
    </div>
  );
}

export function SettingsPage() {
  const { catalog, refreshCatalog } = useApp();
  const id = useId();
  const [saved, setSaved] = useState<Settings | null>(null);
  const [d, setD] = useState<Draft | null>(null);
  const [sys, setSys] = useState<SystemInfo | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const loadSys = async () => {
    try {
      setSys(await api.get<SystemInfo>("/api/system"));
    } catch (e) {
      setErr(errText(e));
    }
  };
  const apply = (s: Settings) => {
    setSaved(s);
    const { model_paths: _mp, ...rest } = s;
    void _mp;
    setD(rest);
  };
  useEffect(() => {
    api.get<Settings>("/api/settings").then(apply, (e) => setErr(errText(e)));
    void loadSys();
    const t = setInterval(() => void loadSys(), 5000);
    return () => clearInterval(t);
  }, []);

  if (!d || !saved) return err ? <ErrorAlert message={err} /> : <p role="status">설정을 불러오는 중…</p>;
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => (x ? { ...x, [k]: v } : x));
  const num = (v: string) => (v === "" ? 0 : Number(v));
  const gpus = sys?.gpus ?? [];
  const allGpus = d.allowed_gpus === null;
  const allowedSet = new Set(d.allowed_gpus ?? []);
  const unknownAllowed = (d.allowed_gpus ?? []).filter((u) => !gpus.some((g) => g.uuid === u));
  const dirty = JSON.stringify(d) !== JSON.stringify((({ model_paths: _x, ...r }) => (void _x, r))(saved));
  const ttsModels = Object.values(catalog?.models ?? {}).filter((m) => m.kind === "tts");
  const asrModels = Object.values(catalog?.models ?? {}).filter((m) => m.kind === "asr");
  const withCurrent = (list: typeof ttsModels, cur: string) => (list.some((m) => m.id === cur) ? list : [...list, { id: cur, label: `${cur} (지금 목록에 없음)` } as (typeof list)[number]]);

  const save = async () => {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const r = await api.put<Settings>("/api/settings", d);
      apply(r);
      setMsg("설정을 저장했습니다");
      await Promise.all([refreshCatalog(), loadSys()]);
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <form
        className="stack"
        aria-label="설정"
        data-testid="settings-form"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <section className="card" aria-labelledby={`${id}-gpu`} data-testid="settings-gpu-section">
          <h2 id={`${id}-gpu`}>GPU</h2>
          <Check
            id={`${id}-allgpu`}
            label="감지된 GPU 전부 사용"
            checked={allGpus}
            testid="settings-all-gpus"
            onChange={(v) => set("allowed_gpus", v ? null : gpus.map((g) => g.uuid))}
            help="끄면 아래에서 체크한 카드만 씁니다(카드는 번호가 아닌 UUID 로 기억합니다)."
          />
          {!gpus.length ? (
            <p className="empty" data-testid="settings-no-gpu">
              감지된 NVIDIA GPU 가 없습니다. CPU 로 돌릴 수 있는 엔진만 씁니다.
            </p>
          ) : (
            <div className="table-wrap">
              <table aria-label="GPU 목록" data-testid="gpu-table">
                <thead>
                  <tr>
                    <th scope="col">사용</th>
                    <th scope="col">번호</th>
                    <th scope="col">이름</th>
                    <th scope="col">UUID</th>
                    <th scope="col">메모리</th>
                    <th scope="col">온도</th>
                    <th scope="col">사용률</th>
                    <th scope="col">지금 못 쓰는 이유</th>
                  </tr>
                </thead>
                <tbody>
                  {gpus.map((g) => {
                    const cid = `${id}-gpu-${g.index}`;
                    const checked = allGpus || allowedSet.has(g.uuid);
                    return (
                      <tr key={g.uuid} data-testid="gpu-row" data-gpu-uuid={g.uuid} data-gpu-index={g.index}>
                        <td>
                          <input
                            id={cid}
                            type="checkbox"
                            checked={checked}
                            disabled={allGpus}
                            aria-label={`GPU${g.index} ${g.name} 사용`}
                            data-testid="gpu-allow"
                            onChange={(e) => {
                              const next = new Set(allowedSet);
                              if (e.target.checked) next.add(g.uuid);
                              else next.delete(g.uuid);
                              set("allowed_gpus", [...next]);
                            }}
                          />
                        </td>
                        <td className="num">{g.index}</td>
                        <th scope="row">{g.name}</th>
                        <td className="mono small">{g.uuid}</td>
                        <td className="mono small">
                          {g.used_gb} / {g.total_gb} GB (여유 {g.free_gb})
                          {g.ours_gb ? <div>우리 것 {g.ours_gb} GB</div> : null}
                          {g.foreign_est_gb ? <div>다른 프로그램 추정 {g.foreign_est_gb} GB</div> : null}
                        </td>
                        <td className="num">{g.temp_c ?? "—"}°C</td>
                        <td className="num">{g.util ?? "—"}%</td>
                        <td data-testid="gpu-blocked">
                          {g.blocked?.length ? g.blocked.map((b) => <Badge key={b} tone="warn">{b}</Badge>) : <Badge tone="ok">사용 가능</Badge>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {!allGpus && allowedSet.size === 0 ? (
            <p className="warn-text small" role="status">
              체크한 카드가 없습니다 — GPU 를 하나도 쓰지 않습니다.
            </p>
          ) : null}
          {unknownAllowed.length ? <p className="small muted">지금 감지되지 않은 카드 {unknownAllowed.length}개도 허용 목록에 남겨 둡니다.</p> : null}
          <div className="grid-fields">
            <Field id={`${id}-gpumode`} label="GPU 모드">
              {(fid) => (
                <select id={fid} value={d.gpu_mode} onChange={(e) => set("gpu_mode", e.target.value as Draft["gpu_mode"])} data-testid="settings-gpu-mode">
                  <option value="auto">auto (허용된 카드 중 여유 있는 곳)</option>
                  <option value="cpu">cpu (GPU 쓰지 않음)</option>
                </select>
              )}
            </Field>
            <Field id={`${id}-reserve`} label="카드마다 남겨 둘 메모리 (GB)">
              {(fid) => <input id={fid} type="number" min={0} step={0.5} value={d.vram_reserve_gb} onChange={(e) => set("vram_reserve_gb", num(e.target.value))} data-testid="settings-vram-reserve" />}
            </Field>
            <Field id={`${id}-foreign`} label="「다른 프로그램 사용 중」 기준 (GB)">
              {(fid) => <input id={fid} type="number" min={0} step={0.5} value={d.foreign_vram_gb} onChange={(e) => set("foreign_vram_gb", num(e.target.value))} data-testid="settings-foreign-vram" />}
            </Field>
            <Field id={`${id}-temp`} label="온도 한계 (°C)">
              {(fid) => <input id={fid} type="number" min={40} max={110} step={1} value={d.temp_limit_c} onChange={(e) => set("temp_limit_c", num(e.target.value))} data-testid="settings-temp-limit" />}
            </Field>
          </div>
          <Check id={`${id}-avoid`} label="다른 프로그램이 쓰는 카드는 피하기" checked={d.avoid_foreign_gpu} onChange={(v) => set("avoid_foreign_gpu", v)} testid="settings-avoid-foreign" />
          <Check id={`${id}-cpu`} label="쓸 GPU 가 없으면 CPU 로 돌릴 수 있는 엔진은 CPU 로" checked={d.allow_cpu} onChange={(v) => set("allow_cpu", v)} testid="settings-allow-cpu" />
        </section>

        <section className="card" aria-labelledby={`${id}-res`} data-testid="settings-general-section">
          <h2 id={`${id}-res`}>모델·작업자</h2>
          <div className="grid-fields">
            <Field id={`${id}-root`} label="모델 루트 (model_root)" help="모델 가중치를 둘 폴더. 모델마다 <루트>/<owner>/<repo> 에 받습니다.">
              {(fid, h) => <input id={fid} type="text" value={d.model_root} onChange={(e) => set("model_root", e.target.value)} aria-describedby={h} data-testid="settings-model-root" />}
            </Field>
            <Field id={`${id}-hf`} label="Hugging Face 주소 (hf_endpoint)" help="비우면 huggingface.co">
              {(fid, h) => <input id={fid} type="text" value={d.hf_endpoint} onChange={(e) => set("hf_endpoint", e.target.value)} aria-describedby={h} data-testid="settings-hf-endpoint" />}
            </Field>
            <Field id={`${id}-idle`} label="유휴 내리기 (분, 0 = 내리지 않음)">
              {(fid) => <input id={fid} type="number" min={0} step={1} value={d.idle_unload_min} onChange={(e) => set("idle_unload_min", num(e.target.value))} data-testid="settings-idle-unload" />}
            </Field>
            <Field id={`${id}-maxres`} label="동시에 올려 둘 작업자 수">
              {(fid) => <input id={fid} type="number" min={1} max={16} step={1} value={d.max_resident} onChange={(e) => set("max_resident", num(e.target.value))} data-testid="settings-max-resident" />}
            </Field>
            <Field id={`${id}-threads`} label="CPU 스레드 (0 = 자동)">
              {(fid) => <input id={fid} type="number" min={0} step={1} value={d.cpu_threads} onChange={(e) => set("cpu_threads", num(e.target.value))} data-testid="settings-cpu-threads" />}
            </Field>
            <Field id={`${id}-dtts`} label="기본 TTS 모델">
              {(fid) => (
                <select id={fid} value={d.default_tts_model} onChange={(e) => set("default_tts_model", e.target.value)} data-testid="settings-default-tts">
                  {withCurrent(ttsModels, d.default_tts_model).map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <Field id={`${id}-dasr`} label="기본 ASR 모델" help="참고 음성 자동 전사·받아쓰기 검증에도 씁니다.">
              {(fid, h) => (
                <select id={fid} value={d.default_asr_model} onChange={(e) => set("default_asr_model", e.target.value)} aria-describedby={h} data-testid="settings-default-asr">
                  {withCurrent(asrModels, d.default_asr_model).map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>
          <Check id={`${id}-test`} label="시험용 엔진 보이기 (모의 TTS·ASR)" checked={d.show_test_engines} onChange={(v) => set("show_test_engines", v)} testid="settings-show-test" />
        </section>

        <div className="row wrap gap sticky-bottom">
          <button type="submit" className="primary" disabled={busy || !dirty}>
            설정 저장
          </button>
          <button type="button" disabled={busy || !dirty} onClick={() => apply(saved)}>
            고친 것 되돌리기
          </button>
          <ConfirmButton
            label="기본값으로"
            confirmLabel="모든 설정을 기본값으로"
            onConfirm={async () => {
              setErr("");
              try {
                apply(await api.post<Settings>("/api/settings/reset"));
                setMsg("설정을 기본값으로 되돌렸습니다");
                await Promise.all([refreshCatalog(), loadSys()]);
              } catch (e) {
                setErr(errText(e));
              }
            }}
          />
          {dirty ? <span className="small warn-text">저장하지 않은 변경이 있습니다</span> : null}
        </div>
        {msg ? (
          <p role="status" className="success" data-testid="settings-status">
            {msg}
          </p>
        ) : null}
        <ErrorAlert message={err} testid="settings-error" />
      </form>

      <section className="card" aria-labelledby={`${id}-sys`} data-testid="system-info">
        <h2 id={`${id}-sys`}>시스템 정보</h2>
        {sys ? (
          <dl className="meta">
            <div>
              <dt>OS</dt>
              <dd>
                {sys.os} ({sys.machine})
              </dd>
            </div>
            <div>
              <dt>CPU</dt>
              <dd>
                {sys.cpu} · 논리 {sys.cpu_count} / 물리 {sys.cpu_physical} · 사용 {sys.cpu_percent}%
              </dd>
            </div>
            <div>
              <dt>RAM</dt>
              <dd>
                {sys.ram_gb} GB (여유 {sys.ram_free_gb} GB)
              </dd>
            </div>
            <div>
              <dt>서비스 버전</dt>
              <dd className="mono" data-testid="system-version">
                {sys.service?.version}
                {sys.service?.git ? ` · ${sys.service.git}` : ""}
                {sys.service?.dirty ? " (dirty)" : ""}
              </dd>
            </div>
            <div>
              <dt>데이터 폴더</dt>
              <dd className="mono small" data-testid="system-data-dir">
                {sys.data_dir}
              </dd>
            </div>
            <div>
              <dt>상주 작업자</dt>
              <dd>{sys.workers?.length ?? 0}개</dd>
            </div>
          </dl>
        ) : (
          <p role="status">불러오는 중…</p>
        )}
      </section>
    </div>
  );
}
