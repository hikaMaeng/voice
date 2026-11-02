import { useEffect, useState } from "react";
import { isActive } from "./api";
import { ErrorAlert } from "./components/ui";
import { useApp } from "./state";
import { ModelsPage } from "./pages/ModelsPage";
import { TtsPage } from "./pages/TtsPage";
import { ResultsPage } from "./pages/ResultsPage";
import { AsrPage } from "./pages/AsrPage";
import { JobsPage } from "./pages/JobsPage";
import { SettingsPage } from "./pages/SettingsPage";

const ROUTES = [
  { key: "models", label: "모델 관리" },
  { key: "tts", label: "TTS" },
  { key: "results", label: "결과물" },
  { key: "asr", label: "ASR" },
  { key: "jobs", label: "작업" },
  { key: "settings", label: "설정" },
] as const;
type RouteKey = (typeof ROUTES)[number]["key"];
// 카탈로그(엔진·모델 스키마)가 있어야 그릴 수 있는 화면
const NEEDS_CATALOG: RouteKey[] = ["models", "tts", "asr"];

function currentRoute(): RouteKey {
  const h = window.location.hash.replace(/^#\/?/, "").split(/[/?]/)[0];
  return (ROUTES.find((r) => r.key === h)?.key ?? "tts") as RouteKey;
}

export function App() {
  const [route, setRoute] = useState<RouteKey>(currentRoute);
  const { jobs, catalog, catalogError } = useApp();
  useEffect(() => {
    const on = () => setRoute(currentRoute());
    window.addEventListener("hashchange", on);
    if (!window.location.hash) window.location.replace("#/tts");
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const active = jobs.filter(isActive).length;
  const label = ROUTES.find((r) => r.key === route)!.label;
  useEffect(() => {
    document.title = `${label} — voice`;
  }, [label]);

  return (
    <>
      <header className="topbar">
        <a className="brand" href="#/tts">
          voice <span className="muted small">로컬 TTS·ASR</span>
        </a>
        <nav aria-label="주 메뉴" data-testid="main-nav">
          <ul>
            {ROUTES.map((r) => (
              <li key={r.key}>
                <a href={`#/${r.key}`} aria-current={route === r.key ? "page" : undefined} data-testid={`nav-${r.key}`}>
                  {r.label}
                  {r.key === "jobs" && active > 0 ? (
                    <span className="count" aria-hidden="true">
                      {active}
                    </span>
                  ) : null}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <p className="active-jobs" role="status" data-testid="active-job-count" data-count={active}>
          실행 중 작업 {active}개
        </p>
      </header>
      <main id="main" data-testid={`page-${route}`} aria-labelledby="page-title">
        <h1 id="page-title">{label}</h1>
        <ErrorAlert message={catalogError ? `카탈로그를 불러오지 못했습니다: ${catalogError}` : ""} testid="catalog-error" />
        {!catalog && !catalogError && NEEDS_CATALOG.includes(route) ? (
          <p role="status" aria-busy="true" data-testid="catalog-pending">
            카탈로그를 불러오는 중… (모델 폴더 확인이 네트워크 드라이브에서 오래 걸릴 수 있습니다)
          </p>
        ) : null}
        {catalog ? (
          <>
            {route === "models" && <ModelsPage />}
            {route === "tts" && <TtsPage />}
            {route === "asr" && <AsrPage />}
          </>
        ) : null}
        {route === "results" && <ResultsPage />}
        {route === "jobs" && <JobsPage />}
        {route === "settings" && <SettingsPage />}
      </main>
    </>
  );
}
