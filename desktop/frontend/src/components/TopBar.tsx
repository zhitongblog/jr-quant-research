import { useEffect, useState } from "react";
import { api, type Health, type JobStatus } from "@/api";
import { Pill } from "@/components/Card";

export function TopBar({ onRefresh }: { onRefresh: () => void }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (!jobId) return;
    const t = setInterval(async () => {
      try {
        const s = await api.runStatus(jobId);
        setJob(s);
        if (s.status === "completed" || s.status === "failed") {
          clearInterval(t);
          if (s.status === "completed") onRefresh();
        }
      } catch (e) {
        console.error(e);
      }
    }, 2000);
    return () => clearInterval(t);
  }, [jobId, onRefresh]);

  const trigger = async () => {
    try {
      const r = await api.runMonthlyUpdate();
      setJobId(r.task_id);
      setJob({ task_id: r.task_id, status: "pending", command: "", tail: [], n_lines: 0 });
    } catch (e) {
      alert(`触发失败: ${e}`);
    }
  };

  return (
    <header className="h-14 border-b border-border bg-panel px-4 flex items-center gap-3">
      <div className="flex-1 flex items-center gap-3">
        {health ? (
          <>
            <Pill tone="up">API ✓</Pill>
            <DataFreshnessPill date={health.data_last_date} />
            <Pill>{health.n_portfolios} 组合 · {health.n_predictions} 预测</Pill>
            <span className="text-xs text-muted font-mono">{health.proj_root}</span>
          </>
        ) : (
          <Pill tone="down">API ✗</Pill>
        )}
      </div>
      <div className="flex items-center gap-3">
        {job && job.status !== "completed" && job.status !== "failed" && (
          <span className="text-xs text-muted">
            {job.status} · {job.n_lines} lines · {job.tail[job.tail.length - 1]?.slice(0, 60)}
          </span>
        )}
        {job?.status === "completed" && <Pill tone="up">完成</Pill>}
        {job?.status === "failed" && <Pill tone="down">失败 rc={job.return_code}</Pill>}
        <button
          type="button"
          onClick={trigger}
          disabled={!!jobId && job?.status !== "completed" && job?.status !== "failed"}
          className="px-3 py-1.5 rounded-md bg-accent/15 hover:bg-accent/25 text-accent border border-accent/40 text-sm disabled:opacity-50 disabled:cursor-not-allowed transition"
        >
          {job?.status === "running" || job?.status === "pending"
            ? "更新中..."
            : "立即跑月度更新"}
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
