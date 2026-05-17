import { useEffect, useState } from "react";
import { api, type Health, type Portfolio, type PerformanceRow } from "@/api";
import { Card, CardBody, CardHeader, Pill } from "@/components/Card";
import { fmtMoney, useProfile, RISK_PROFILE } from "@/profile";
import type { ViewKey } from "@/App";

export function OverviewView({
  refreshKey,
  onNavigate,
}: {
  refreshKey: number;
  onNavigate: (v: ViewKey) => void;
}) {
  const [profile] = useProfile();
  const [health, setHealth] = useState<Health | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [perf, setPerf] = useState<PerformanceRow[] | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.portfolioLatest().then(setPortfolio).catch(() => setPortfolio(null));
    api.performanceTimeseries().then((r) => setPerf(r.rows)).catch(() => setPerf([]));
  }, [refreshKey]);

  const risk = RISK_PROFILE[profile.riskTolerance];
  const invested = profile.capital * (1 - profile.cashReservePct);
  const worstCaseLoss = invested * risk.expectedMaxDD;
  const suggestedInvest = profile.capital * risk.suggestedAllocation;

  const lastEval = perf && perf.length > 0 ? perf[perf.length - 1] : null;

  const missing: string[] = [];
  if (profile.capital === 0) missing.push("本金");
  if (!profile.acceptedRiskWarning) missing.push("勾选风险声明");
  const needsSetup = missing.length > 0;

  return (
    <div className="p-6 space-y-6 overflow-auto">
      <div>
        <h1 className="text-2xl font-semibold text-fg">概览</h1>
        <div className="text-sm text-muted mt-1">
          {portfolio ? `最新模型更新 ${portfolio.date}` : "未加载组合数据"}
        </div>
      </div>

      {needsSetup && (
        <Card className="border-down/40">
          <CardHeader
            title={`⚠️ 还缺：${missing.join(" + ")}`}
            subtitle={
              missing.includes("勾选风险声明") && !missing.includes("本金")
                ? "本金已填，但 ① 卡片底部的「我已阅读风险声明」复选框还没勾"
                : "去设置页补齐"
            }
          />
          <CardBody>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => onNavigate("settings")}
                className="px-4 py-2 rounded-md bg-accent/15 hover:bg-accent/25 text-accent border border-accent/40 text-sm"
              >
                去设置 →
              </button>
              <span className="text-xs text-muted">
                当前已设置：本金 {profile.capital > 0 ? "✓" : "✗"} · 风险等级 ✓ · 声明 {profile.acceptedRiskWarning ? "✓" : "✗"}
              </span>
            </div>
          </CardBody>
        </Card>
      )}

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardHeader title="资金状况" right={<Pill tone="accent">{risk.label}</Pill>} />
          <CardBody>
            {profile.capital === 0 ? (
              <div className="text-sm text-muted">未设置本金</div>
            ) : (
              <div className="space-y-2 text-sm">
                <Row label="本金" value={fmtMoney(profile.capital)} />
                <Row label="计划投入" value={fmtMoney(invested)} tone="accent" />
                <Row label="现金保留" value={fmtMoney(profile.capital - invested)} />
                <Row label="按风险建议上限"
                  value={fmtMoney(suggestedInvest)}
                  tone={invested > suggestedInvest ? "down" : "up"}
                  hint={invested > suggestedInvest ? "超出建议上限" : "在建议范围内"}
                />
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="风险预警" />
          <CardBody>
            {profile.capital === 0 ? (
              <div className="text-sm text-muted">未设置本金</div>
            ) : (
              <div className="space-y-2 text-sm">
                <Row label="最坏回撤预期"
                  value={`-${(risk.expectedMaxDD * 100).toFixed(0)}%`} tone="down" />
                <Row label="对应金额损失"
                  value={fmtMoney(-worstCaseLoss)} tone="down" />
                <div className="text-xs text-muted mt-3 leading-relaxed">
                  {risk.description}
                  <br />
                  如果你的真实承受度跟标签不符，去设置页改风险等级。
                </div>
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="上月战绩" subtitle="vs 沪深300" />
          <CardBody>
            {!perf || perf.length === 0 ? (
              <div className="text-sm text-muted leading-relaxed">
                尚无月度评估。<br />
                第二次月度更新（≥25 天后）才会自动评估上一期持仓。
              </div>
            ) : lastEval ? (
              <div className="space-y-2 text-sm">
                <Row label="评估期间"
                  value={`${lastEval.prediction_date} → ${lastEval.eval_date ?? "?"}`} />
                <Row label="CSI300 涨跌"
                  value={lastEval.csi300_cum_ret != null ? `${(lastEval.csi300_cum_ret * 100).toFixed(2)}%` : "—"} />
                <Row label="Ensemble 超额"
                  value={lastEval.ensemble_excess != null
                    ? `${lastEval.ensemble_excess >= 0 ? "+" : ""}${(lastEval.ensemble_excess * 100).toFixed(2)}%`
                    : "—"}
                  tone={lastEval.ensemble_excess != null
                    ? (lastEval.ensemble_excess >= 0 ? "up" : "down") : undefined} />
              </div>
            ) : null}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="本月模型推荐"
          subtitle={portfolio ? `Ensemble 共 ${portfolio.ensemble.holdings.length} 只持仓` : "尚未加载"}
          right={
            <button
              type="button"
              onClick={() => onNavigate("trades")}
              disabled={!portfolio || profile.capital === 0}
              className="px-3 py-1.5 rounded-md bg-accent/15 hover:bg-accent/25 text-accent border border-accent/40 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
            >
              生成操作单 →
            </button>
          }
        />
        <CardBody>
          {portfolio ? (
            <div className="space-y-3">
              <div className="text-sm text-muted">
                <strong className="text-fg">{portfolio.path_d.llm_picks.length}</strong> 个被 LLM 推荐的行业：
                {portfolio.path_d.llm_picks.map((p) => (
                  <span key={p.sw1_code} className="ml-2 text-accent">
                    {p.sw1_name}
                  </span>
                ))}
              </div>
              {portfolio.path_d.llm_macro && (
                <div className="text-xs text-fg/90 border-l-2 border-accent/40 pl-3 leading-relaxed">
                  {portfolio.path_d.llm_macro}
                </div>
              )}
            </div>
          ) : (
            <div className="text-sm text-muted">未加载</div>
          )}
        </CardBody>
      </Card>

      <Card className="border-down/30">
        <CardHeader title="实盘前必读"
          subtitle="花 1 分钟读完这段比写代码更重要" />
        <CardBody>
          <ol className="text-sm text-fg/90 space-y-2 leading-relaxed list-decimal pl-5">
            <li>
              <strong className="text-fg">本模型只在牛市验证过</strong>。
              历史数据上 +33% / Sharpe 2.58 是 2025-07 ~ 2026-05 单边上涨期间的成绩，
              熊市表现完全未知，**可能跑输基准 10-20%**。
            </li>
            <li>
              <strong className="text-fg">最稳妥的做法是定投沪深 300 ETF (510300)</strong>，
              年化预期 6-9%、心理压力最小。如果你拿不准，请优先选这条路。
            </li>
            <li>
              <strong className="text-fg">本系统适合"研究 + 小仓位试探"</strong>。
              建议先用模拟账户跟 6 个月，看每月超额收益是不是稳定为正再考虑实盘。
            </li>
            <li>
              <strong className="text-fg">每月 1 号自动更新</strong> 可以在设置页找到 PowerShell 命令注册。
              不更新的话持仓建议会过期。
            </li>
            <li>
              <strong className="text-fg">永远不要把房贷、教育金、应急金投进来</strong>。
            </li>
          </ol>
        </CardBody>
      </Card>

      {health && (
        <div className="text-xs text-muted font-mono">
          API: {health.proj_root} · {health.n_portfolios} 组合 · {health.n_predictions} 预测
        </div>
      )}
    </div>
  );
}

function Row({
  label, value, tone, hint,
}: { label: string; value: string; tone?: "up" | "down" | "accent"; hint?: string }) {
  const cls = tone === "up" ? "text-up" : tone === "down" ? "text-down" : tone === "accent" ? "text-accent" : "text-fg";
  return (
    <div className="flex items-baseline justify-between border-b border-border/30 py-1">
      <span className="text-muted text-xs">{label}</span>
      <span className={`${cls} font-mono`}>
        {value}
        {hint && <span className="ml-2 text-[10px] text-muted">({hint})</span>}
      </span>
    </div>
  );
}
