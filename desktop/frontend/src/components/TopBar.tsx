import { useEffect, useRef, useState } from "react";
import { api, type Health, type JobStatus } from "@/api";
import { Pill } from "@/components/Card";

type JobKind = "refresh_prices" | "monthly_update";

export function TopBar({ onRefresh }: { onRefresh: () => void }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [jobKind, setJobKind] = useState<JobKind | null>(null);
  // When true, after a successful refresh_prices the monthly_update will auto-fire
  const chainMonthlyAfterPrices = useRef(false);

  const refreshHealth = () => api.health().then(setHealth).catch(() => setHealth(null));
  useEffect(() => { refreshHealth(); }, []);

  useEffect(() => {
    if (!jobId) return;
    const t = setInterval(async () => {
      try {
        const s = await api.runStatus(jobId);
        setJob(s);
        if (s.status === "completed" || s.status === "failed") {
          clearInterval(t);
          if (s.status === "completed") {
            refreshHealth();
            onRefresh();
            // If we were chaining, fire monthly update next
            if (jobKind === "refresh_prices" && chainMonthlyAfterPrices.current) {
              chainMonthlyAfterPrices.current = false;
              try {
                const r = await api.runMonthlyUpdate();
                setJobId(r.task_id);
                setJobKind("monthly_update");
                setJob({ task_id: r.task_id, status: "pending", command: "", tail: [], n_lines: 0 });
              } catch (e) {
                alert(`月度更新触发失败: ${e}`);
              }
            }
          }
        }
      } catch (e) {
        console.error(e);
      }
    }, 2000);
    return () => clearInterval(t);
  }, [jobId, jobKind, onRefresh]);

  const triggerRefreshPrices = async () => {
    chainMonthlyAfterPrices.current = false;
    try {
      const r = await api.refreshPrices();
      setJobId(r.task_id);
      setJobKind("refresh_prices");
      setJob({ task_id: r.task_id, status: "pending", command: "", tail: [], n_lines: 0 });
    } catch (e) {
      alert(`刷新行情失败: ${e}`);
    }
  };

  const triggerFullUpdate = async () => {
    // Chained: refresh prices first, then monthly update
    chainMonthlyAfterPrices.current = true;
    try {
      const r = await api.refreshPrices();
      setJobId(r.task_id);
      setJobKind("refresh_prices");
      setJob({ task_id: r.task_id, status: "pending", command: "", tail: [], n_lines: 0 });
    } catch (e) {
      alert(`触发失败: ${e}`);
    }
  };

  const busy = !!jobId && job?.status !== "completed" && job?.status !== "failed";
  const kindLabel = jobKind === "refresh_prices" ? "拉行情" : "跑模型+LLM";

  return (
    <header className="h-14 border-b border-border bg-panel px-4 flex items-center gap-3">
      <div className="flex-1 flex items-center gap-3">
        {health ? (
          <>
            <Pill tone="up">API ✓</Pill>
            <DataFreshnessPill date={health.data_last_date} />
            <Pill>{health.n_portfolios} 组合 · {health.n_predictions} 预测</Pill>
          </>
        ) : (
          <Pill tone="down">API ✗</Pill>
        )}
      </div>
      <div className="flex items-center gap-2">
        {busy && (
          <span className="text-xs text-muted">
            {kindLabel} · {job?.n_lines} lines · {job?.tail[job.tail.length - 1]?.slice(0, 50)}
          </span>
        )}
        {!busy && job?.status === "completed" && <Pill tone="up">完成</Pill>}
        {!busy && job?.status === "failed" && <Pill tone="down">失败 rc={job.return_code}</Pill>}
        <button
          type="button"
          onClick={triggerRefreshPrices}
          disabled={busy}
          title="只拉最新行情数据 (~30 秒)"
          className="px-2.5 py-1.5 rounded-md bg-panel-2 hover:bg-panel-2/70 text-fg border border-border text-xs disabled:opacity-40"
        >
          🔄 刷新行情
        </button>
        <button
          type="button"
          onClick={triggerFullUpdate}
          disabled={busy}
          title="先拉最新行情，再跑 LightGBM + LLM 生成新组合 (~3-5 分钟)"
          className="px-3 py-1.5 rounded-md bg-accent/15 hover:bg-accent/25 text-accent border border-accent/40 text-sm disabled:opacity-50 disabled:cursor-not-allowed transition"
        >
          {busy ? (kindLabel + "中...") : "📊 月度更新"}
        </button>
      </div>
    </header>
  );
}

function DataFreshnessPill({ date }: { date: string | null }) {
  if (!date) return <Pill tone="down">数据缺失</Pill>;
  const d = new Date(date);
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  const tone: "up" | "neutral" | "down" =
    days <= 3 ? "up" : days <= 14 ? "neutral" : "down";
  const label = days <= 0 ? "今日" : `${days} 天前`;
  return <Pill tone={tone}>数据 {date} ({label})</Pill>;
}
