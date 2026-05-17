import { useEffect, useState } from "react";
import { api, type NewsRecent, type JobStatus } from "@/api";
import { Card, CardBody, CardHeader, Pill } from "@/components/Card";

export function NewsView({ refreshKey }: { refreshKey: number }) {
  const [news, setNews] = useState<NewsRecent | null>(null);
  const [context, setContext] = useState("");
  const [ctxDirty, setCtxDirty] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = () => {
    setError(null);
    api.newsRecent(50).then(setNews).catch((e) => setError(String(e)));
    api.newsContextGet().then((r) => { setContext(r.text); setCtxDirty(false); })
      .catch(() => { /* ignore */ });
  };

  useEffect(reload, [refreshKey]);

  useEffect(() => {
    if (!jobId) return;
    const t = setInterval(async () => {
      try {
        const s = await api.runStatus(jobId);
        setJob(s);
        if (s.status === "completed" || s.status === "failed") {
          clearInterval(t);
          if (s.status === "completed") {
            reload();
            setSavedMsg("✓ 新闻已刷新");
            setTimeout(() => setSavedMsg(null), 2000);
          }
        }
      } catch (e) { console.error(e); }
    }, 2000);
    return () => clearInterval(t);
  }, [jobId]);

  const refresh = async () => {
    try {
      const r = await api.newsRefresh();
      setJobId(r.task_id);
      setJob({ task_id: r.task_id, status: "pending", command: "", tail: [], n_lines: 0 });
    } catch (e) {
      alert(`触发失败: ${e}`);
    }
  };

  const saveContext = async () => {
    try {
      await api.newsContextSet(context);
      setCtxDirty(false);
      setSavedMsg("✓ 已保存，下次月度更新会注入");
      setTimeout(() => setSavedMsg(null), 2500);
    } catch (e) {
      alert(`保存失败: ${e}`);
    }
  };

  return (
    <div className="p-6 space-y-6 overflow-auto">
      <div className="flex items-baseline gap-3">
        <h1 className="text-2xl font-semibold text-fg">新闻面 / LLM 上下文</h1>
        <Pill>{news?.n_items ?? 0} 条聚合新闻</Pill>
        {news?.refreshed_at && (
          <span className="text-xs text-muted">
            最近刷新 {news.refreshed_at.replace("T", " ")}
          </span>
        )}
      </div>

      <Card>
        <CardHeader
          title="① 你自己的近况摘要 (优先级最高)"
          subtitle="月度更新时会把这段文字注入 LLM prompt。比自动新闻更精准、更有针对性。"
          right={ctxDirty
            ? <Pill tone="down">未保存</Pill>
            : <Pill tone="up">已保存</Pill>
          }
        />
        <CardBody className="space-y-3">
          <textarea
            value={context}
            onChange={(e) => { setContext(e.target.value); setCtxDirty(true); }}
            rows={8}
            placeholder={`示例（200-500 字最合适）：
近期央行公开市场净投放，7月15日全面降准0.5pct。
房地产新政：一线城市认房不认贷，二套首付20%。
新能源车补贴政策5月底到期，部分车企抢装。
特朗普关税升级，半导体板块承压。
关注Q1业绩超预期个股：宁德、海光等。`}
            className="w-full px-3 py-2 bg-panel-2 border border-border rounded-md text-sm font-sans focus:outline-none focus:border-accent/60 leading-relaxed resize-y"
          />
          <div className="flex items-center justify-between">
            <div className="text-xs text-muted">
              {context.length} 字符（建议 200-2000 字，超出会被截断）
            </div>
            <button
              type="button"
              onClick={saveContext}
              disabled={!ctxDirty}
              className="px-4 py-1.5 rounded-md bg-accent/15 hover:bg-accent/25 text-accent border border-accent/40 text-sm disabled:opacity-40"
            >
              保存
            </button>
          </div>
          {savedMsg && <div className="text-xs text-up">{savedMsg}</div>}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="② 自动聚合新闻 (来自财新 / CCTV / 百度)"
          subtitle="LLM 也会看到这部分内容，作为你手动摘要的补充。"
          right={
            <button
              type="button"
              onClick={refresh}
              disabled={!!jobId && job?.status !== "completed" && job?.status !== "failed"}
              className="px-3 py-1.5 rounded-md bg-accent/15 hover:bg-accent/25 text-accent border border-accent/40 text-sm disabled:opacity-40"
            >
              {job?.status === "running" || job?.status === "pending"
                ? "拉取中..."
                : "刷新新闻"}
            </button>
          }
        />
        <CardBody>
          {error && <div className="text-down text-sm mb-3">{error}</div>}

          {job && job.status !== "completed" && job.status !== "failed" && (
            <div className="mb-3 text-xs bg-panel-2 p-2 rounded border border-border">
              <div className="text-muted">{job.status} · {job.n_lines} lines</div>
              <div className="font-mono text-fg/70 mt-1 truncate">
                {job.tail[job.tail.length - 1] ?? ""}
              </div>
            </div>
          )}

          {!news || news.n_items === 0 ? (
            <div className="text-sm text-muted leading-relaxed">
              {news?.message ?? "尚无新闻缓存，点右上「刷新新闻」。需要 30-60 秒。"}
            </div>
          ) : (
            <>
              {news.by_source && (
                <div className="flex gap-2 mb-3 text-xs">
                  {Object.entries(news.by_source).map(([src, n]) => (
                    <Pill key={src}>{src} ({n})</Pill>
                  ))}
                </div>
              )}
              <div className="space-y-2 max-h-[480px] overflow-y-auto">
                {news.items.map((item, i) => (
                  <div key={i} className="border-b border-border/30 pb-2">
                    <div className="flex items-center gap-2 text-[11px] text-muted mb-0.5">
                      <span className="font-mono">{item.date || "?"}</span>
                      <span className="px-1.5 py-0.5 rounded bg-panel-2">{item.source}</span>
                    </div>
                    <div className="text-sm text-fg leading-snug">{item.title}</div>
                    {item.summary && (
                      <div className="text-xs text-muted mt-1 leading-relaxed">
                        {item.summary}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="说明" />
        <CardBody>
          <div className="text-xs text-muted leading-relaxed space-y-2">
            <p>
              <strong className="text-fg">为什么需要新闻？</strong> A 股策略对政策极敏感，
              但纯量价 + LightGBM 模型完全看不到新闻。LLM (DeepSeek) 有训练截止知识，
              但训练后的最新事件不知道。把近况注入 prompt 能补上这块。
            </p>
            <p>
              <strong className="text-fg">优先级</strong>：① 用户摘要 &gt; ② 自动聚合。
              你写的"近期央行降准 0.5pct"比 100 条财新标题信息密度高得多。
            </p>
            <p>
              <strong className="text-fg">什么时候用</strong>：在点"立即跑月度更新"按钮之前，
              先来这页保存你的近况摘要，再回去触发更新。LLM 拿到的就是带新闻的版本。
            </p>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
