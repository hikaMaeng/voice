import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api, errText, isActive, isFinished } from "./api";
import type { Catalog, Generation, Job } from "./api";

/** 결과물 「불러오기」가 TTS 폼에 넘기는 값. 범위: 이 탭 하나, 수명: TTS 화면이 받아 갈 때까지, 지우는 주체: TTS 화면(consumeLoad). */
export interface TtsLoad {
  generation: Generation;
  nonce: number;
}

interface AppState {
  catalog: Catalog | null;
  catalogError: string;
  /** 카탈로그 갱신 중(모델 폴더 확인이 네트워크 드라이브에서 10초 넘게 걸릴 수 있다) */
  catalogLoading: boolean;
  refreshCatalog: () => Promise<void>;
  jobs: Job[];
  refreshJobs: () => Promise<void>;
  ttsLoad: TtsLoad | null;
  requestTtsLoad: (g: Generation) => void;
  consumeTtsLoad: () => void;
}

const Ctx = createContext<AppState | null>(null);

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("AppProvider 밖");
  return v;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [ttsLoad, setTtsLoad] = useState<TtsLoad | null>(null);

  const refreshCatalog = useCallback(async () => {
    setCatalogLoading(true);
    try {
      setCatalog(await api.get<Catalog>("/api/catalog"));
      setCatalogError("");
    } catch (e) {
      setCatalogError(errText(e));
    } finally {
      setCatalogLoading(false);
    }
  }, []);

  const refreshJobs = useCallback(async () => {
    try {
      setJobs(await api.get<Job[]>("/api/jobs"));
    } catch {
      /* 다음 폴링에서 다시 */
    }
  }, []);

  useEffect(() => {
    void refreshCatalog();
  }, [refreshCatalog]);

  // 작업 목록: 실행 중 작업이 있으면 1초, 없으면 3초마다
  const activeRef = useRef(false);
  activeRef.current = jobs.some(isActive);
  useEffect(() => {
    let stop = false;
    let t: ReturnType<typeof setTimeout>;
    const tick = async () => {
      await refreshJobs();
      if (!stop) t = setTimeout(tick, activeRef.current ? 1000 : 3000);
    };
    void tick();
    return () => {
      stop = true;
      clearTimeout(t);
    };
  }, [refreshJobs]);

  const requestTtsLoad = useCallback((g: Generation) => {
    setTtsLoad({ generation: g, nonce: Date.now() });
    window.location.hash = "#/tts";
  }, []);
  const consumeTtsLoad = useCallback(() => setTtsLoad(null), []);

  return (
    <Ctx.Provider value={{ catalog, catalogError, catalogLoading, refreshCatalog, jobs, refreshJobs, ttsLoad, requestTtsLoad, consumeTtsLoad }}>
      {children}
    </Ctx.Provider>
  );
}

/** 작업 하나를 1초마다 본다(끝나면 멈춘다). */
export function useJob(id: string | null): Job | null {
  const [job, setJob] = useState<Job | null>(null);
  useEffect(() => {
    setJob(null);
    if (!id) return;
    let stop = false;
    let t: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const j = await api.get<Job>(`/api/jobs/${id}`);
        if (stop) return;
        setJob(j);
        if (!isFinished(j)) t = setTimeout(tick, 1000);
      } catch {
        if (!stop) t = setTimeout(tick, 2000);
      }
    };
    void tick();
    return () => {
      stop = true;
      clearTimeout(t);
    };
  }, [id]);
  return job;
}

/** 간단한 비동기 목록 불러오기. */
export function useLoader<T>(path: string | null, initial: T) {
  const [data, setData] = useState<T>(initial);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      setData(await api.get<T>(path));
      setError("");
    } catch (e) {
      setError(errText(e));
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { data, setData, error, loading, reload };
}
