import { useEffect, useMemo, useState } from "react";
import { api, type Portfolio, type PriceLatestRow } from "@/api";
import { Card, CardBody, CardHeader, Pill } from "@/components/Card";
import {
  fmtMoney, useProfile, RISK_PROFILE,
  deriveHoldingCount, MIN_PER_HOLDING, MIN_CAPITAL, MAX_HOLDINGS,
} from "@/profile";

type StrategyKey = "ensemble" | "path_a" | "path_d";

interface Plan {
  qlib_symbol: string;
  symbol: string;
  name: string;
  sw1_name: string;
  close: number | null;
  buy_max: number | null;
  buy_floor: number | null;
  target_amount: number;
  shares: number;
  actual_amount: number;
  status: "buy" | "expensive" | "no_price" | "skipped";
}

const ROUND_LOT = 100;

export function TradeListView({
  refreshKey,
  onSelectSymbol,
}: {
  refreshKey: number;
  onSelectSymbol?: (s: string) => void;
}) {
  const [profile, updateProfile] = useProfile();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [prices, setPrices] = useState<Record<string, PriceLatestRow>>({});
  const [strategy, setStrategy] = useState<StrategyKey>("ensemble");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    setPortfolio(null);
    api.portfolioLatest()
      .then(setPortfolio)
      .catch((e) => setError(String(e)));
  }, [refreshKey]);

  useEffect(() => {
    if (!portfolio) return;
    const all = [
      ...portfolio.path_a.holdings,
      ...portfolio.path_d.holdings,
      ...portfolio.ensemble.holdings,
    ].map((h) => h.qlib_symbol);
    const unique = Array.from(new Set(all));
    if (!unique.length) return;
    api.pricesLatest(unique)
      .then((r) => {
        const map: Record<string, PriceLatestRow> = {};
        for (const row of r.rows) map[row.qlib_symbol] = row;
        setPrices(map);
      })
      .catch((e) => setError(String(e)));
  }, [portfolio]);

  // ---------- Capital + holding count ----------
  const invested = profile.capital * (1 - profile.cashReservePct);
  const autoK = deriveHoldingCount(profile.capital, profile.cashReservePct);
  const effectiveK = profile.numHoldings === "auto"
    ? autoK
    : Math.min(MAX_HOLDINGS, Math.max(1, profile.numHoldings));
  const usingAuto = profile.numHoldings === "auto";

  const holdings = useMemo(() => {
    if (!portfolio) return [];
    return portfolio[strategy].holdings.slice(0, effectiveK);
  }, [portfolio, strategy, effectiveK]);

  const targetPerName = holdings.length ? invested / holdings.length : 0;
  const bandPct = profile.buyBandPct;

  const plans = useMemo<Plan[]>(() => {
    return holdings.map((h) => {
      const px = prices[h.qlib_symbol]?.close ?? null;
      const buyMax = px ? px * (1 + bandPct) : null;
      const buyFloor = px ? px * (1 - bandPct) : null;
      if (!px || px <= 0) {
        return {
          qlib_symbol: h.qlib_symbol, symbol: h.symbol, name: h.name, sw1_name: h.sw1_name,
          close: px, buy_max: buyMax, buy_floor: buyFloor,
          target_amount: targetPerName, shares: 0, actual_amount: 0, status: "no_price",
        };
      }
      const oneLotCost = px * ROUND_LOT;
      // If even one lot exceeds target, mark as expensive (skip)
      if (oneLotCost > targetPerName * 1.5) {
        return {
          qlib_symbol: h.qlib_symbol, symbol: h.symbol, name: h.name, sw1_name: h.sw1_name,
          close: px, buy_max: buyMax, buy_floor: buyFloor,
          target_amount: targetPerName, shares: 0, actual_amount: 0, status: "expensive",
        };
      }
      const rawShares = Math.floor(targetPerName / px);
      const shares = Math.max(0, Math.floor(rawShares / ROUND_LOT) * ROUND_LOT);
      return {
        qlib_symbol: h.qlib_symbol, symbol: h.symbol, name: h.name, sw1_name: h.sw1_name,
        close: px, buy_max: buyMax, buy_floor: buyFloor,
        target_amount: targetPerName,
        shares,
        actual_amount: shares * px,
        status: shares > 0 ? "buy" : "skipped",
      };
    });
  }, [holdings, prices, targetPerName, bandPct]);

  const buyPlans = plans.filter((p) => p.status === "buy");
  const totalPlanned = buyPlans.reduce((acc, p) => acc + p.actual_amount, 0);
  const idleCash = invested - totalPlanned;
  const buyCost = totalPlanned * 0.0013;
  const risk = RISK_PROFILE[profile.riskTolerance];
  const worstCaseLoss = invested * risk.expectedMaxDD;

  // Industry distribution (after slicing to top-K)
  const industries = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of buyPlans) {
      const k = p.sw1_name || "未分类";
      m.set(k, (m.get(k) ?? 0) + 1);
    }
    return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
  }, [buyPlans]);

  // ---------- Gating ----------
  if (!profile.capital) {
    return (
      <div className="p-6 max-w-2xl">
        <Card>
          <CardHeader title="先设置本金"
            subtitle="未设置本金前无法生成操作单——去设置页填一下" />
          <CardBody>
            <div className="text-sm text-muted leading-relaxed">
              在左侧栏点击"设置"，填写本金和风险承受度。本金至少 {fmtMoney(MIN_CAPITAL)}，
              否则按 A 股 100 股一手限制根本买不了几只票。
            </div>
          </CardBody>
        </Card>
      </div>
    );
  }
  if (profile.capital < MIN_CAPITAL) {
    return (
      <div className="p-6 max-w-2xl">
        <Card className="border-down/40">
          <CardHeader title={`本金过低（${fmtMoney(profile.capital)}）`}
            subtitle={`A 股每只最少 100 股，按当前本金根本下不了单`} />
          <CardBody>
            <div className="text-sm text-fg/90 leading-relaxed space-y-2">
              <p>
                建议本金至少 <strong className="text-fg">{fmtMoney(MIN_CAPITAL)}</strong>。
                即便如此，按等权也只能买 {deriveHoldingCount(MIN_CAPITAL, 0.2)} 只票，
                分散度仍然偏低。
              </p>
              <p>
                替代方案：直接定投 <strong className="text-accent">沪深300 ETF (510300)</strong>。
                1 手起步价 ~¥400，¥{profile.capital.toLocaleString()} 完全够定投，
                而且无须每月调仓。
              </p>
            </div>
          </CardBody>
        </Card>
      </div>
    );
  }

  if (error) return <div className="p-6 text-down text-sm">加载失败：{error}</div>;
  if (!portfolio) return <div className="p-6 text-muted text-sm">加载中…</div>;

  return (
    <div className="p-6 space-y-6 overflow-auto">
      <div className="flex items-baseline gap-3">
        <h1 className="text-2xl font-semibold text-fg">今日操作单</h1>
        <Pill>{portfolio.date}</Pill>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <SummaryCard label="本金" value={fmtMoney(profile.capital)} />
        <SummaryCard
          label={`计划投入 (${((1 - profile.cashReservePct) * 100).toFixed(0)}%)`}
          value={fmtMoney(invested)}
          accent
        />
        <SummaryCard
          label={`持仓数（${usingAuto ? "自动" : "手动"}）`}
          value={`${effectiveK} 只`}
          hint={usingAuto ? `按每只 ≥${fmtMoney(MIN_PER_HOLDING)}` : "已手动指定"}
        />
        <SummaryCard
          label={`最坏回撤（${risk.label}）`}
          value={`-${fmtMoney(worstCaseLoss)} (-${(risk.expectedMaxDD * 100).toFixed(0)}%)`}
          tone="down"
        />
      </div>

      <Card>
        <CardHeader
          title="持仓数与买入区间"
          subtitle="对小本金集中度有决定性影响"
        />
        <CardBody className="space-y-4">
          <div>
            <div className="flex justify-between mb-1">
              <span className="text-xs text-muted">持仓数</span>
              <span className="text-xs font-mono">
                <button
                  type="button"
                  onClick={() => updateProfile({ numHoldings: "auto" })}
                  className={`px-2 py-0.5 rounded text-[10px] mr-2 ${
                    usingAuto ? "bg-accent/20 text-accent" : "bg-panel-2 text-muted hover:text-fg"
                  }`}
                >
                  自动 ({autoK})
                </button>
                <span className={usingAuto ? "text-muted" : "text-fg"}>{effectiveK} 只</span>
              </span>
            </div>
            <input
              type="range"
              min={1} max={MAX_HOLDINGS} step={1}
              value={effectiveK}
              onChange={(e) => updateProfile({ numHoldings: Number(e.target.value) })}
              className="w-full accent-accent"
            />
            <div className="text-[11px] text-muted mt-1">
              本金 ÷ 持仓数 = 每只 {fmtMoney(invested / effectiveK)}。
              低于 ¥2000/只时几乎只能买最便宜的几只票。
            </div>
          </div>
          <div>
            <div className="flex justify-between mb-1">
              <span className="text-xs text-muted">买入价格带（昨收 ±%）</span>
              <span className="text-xs font-mono text-fg">±{(bandPct * 100).toFixed(1)}%</span>
            </div>
            <input
              type="range"
              min={0.005} max={0.10} step={0.005}
              value={bandPct}
              onChange={(e) => updateProfile({ buyBandPct: Number(e.target.value) })}
              className="w-full accent-accent"
            />
            <div className="text-[11px] text-muted mt-1">
              开盘价高于上限 → 等回调或跳过，避免追高；低于下限 → 也可能是基本面有问题，谨慎接刀
            </div>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="选择跟随的策略"
          subtitle="不同策略适合不同 conviction 水平"
          right={
            <div className="flex gap-1.5">
              {(["ensemble", "path_a", "path_d"] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setStrategy(k)}
                  className={`px-2.5 py-1 rounded-md text-xs border transition ${
                    strategy === k
                      ? "bg-accent/15 text-accent border-accent/40"
                      : "bg-panel border-border text-muted hover:text-fg"
                  }`}
                >
                  {k === "ensemble" ? "Ensemble" : k === "path_a" ? "Path A 量价" : "Path D LLM"}
                </button>
              ))}
            </div>
          }
        />
        <CardBody>
          <div className="text-sm text-muted">
            {strategy === "ensemble" && "A∩D 交集（强共识）+ 余下用 Path A 补齐，分散度最高，新手默认选这个"}
            {strategy === "path_a" && "纯量价 + 行业 LightGBM 模型选股，回测最强但单边市风险"}
            {strategy === "path_d" && "DeepSeek-V4 选 top-3 行业，仅 ~20 只票，集中度高 conviction 强"}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title={`等权操作单 · top ${effectiveK} 只`}
          subtitle={`每只目标 ${fmtMoney(targetPerName)}，A 股 100 股一手向下取整`}
          right={
            <span className="text-xs">
              <span className="text-muted">实际投入 </span>
              <span className="text-accent font-mono">{fmtMoney(totalPlanned)}</span>
              <span className="text-muted"> · 闲置 </span>
              <span className="text-fg font-mono">{fmtMoney(idleCash)}</span>
              <span className="text-muted"> · 双边成本 ~</span>
              <span className="text-down font-mono">{fmtMoney(buyCost)}</span>
            </span>
          }
        />
        <CardBody>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted text-xs border-b border-border">
                <th className="text-left py-2 font-normal">代码 · 名称</th>
                <th className="text-left py-2 font-normal">行业</th>
                <th className="text-right py-2 font-normal">昨收</th>
                <th className="text-right py-2 font-normal">买入区间</th>
                <th className="text-right py-2 font-normal">股数</th>
                <th className="text-right py-2 font-normal">金额</th>
                <th className="text-right py-2 font-normal">状态</th>
              </tr>
            </thead>
            <tbody>
              {plans.map((p) => (
                <tr
                  key={p.qlib_symbol}
                  onClick={() => onSelectSymbol?.(p.qlib_symbol)}
                  className={`border-b border-border/30 cursor-pointer hover:bg-panel-2/40 ${
                    p.status === "buy" ? "" : "opacity-60"
                  }`}
                >
                  <td className="py-2">
                    <div className="font-mono text-xs text-muted">{p.symbol}</div>
                    <div className="text-fg">{p.name || "—"}</div>
                  </td>
                  <td className="py-2 text-muted text-xs">{p.sw1_name}</td>
                  <td className="py-2 text-right font-mono">
                    {p.close ? `¥${p.close.toFixed(2)}` : "—"}
                  </td>
                  <td className="py-2 text-right font-mono text-[11px]">
                    {p.buy_floor && p.buy_max
                      ? <>
                          <span className="text-up">¥{p.buy_floor.toFixed(2)}</span>
                          <span className="text-muted"> ~ </span>
                          <span className="text-down">¥{p.buy_max.toFixed(2)}</span>
                        </>
                      : "—"}
                  </td>
                  <td className="py-2 text-right font-mono text-accent">
                    {p.shares ? `${p.shares} (${p.shares / 100}手)` : "—"}
                  </td>
                  <td className="py-2 text-right font-mono">
                    {p.actual_amount ? fmtMoney(p.actual_amount) : "—"}
                  </td>
                  <td className="py-2 text-right">
                    <StatusPill status={p.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>

      {industries.length > 0 && (
        <Card>
          <CardHeader title="行业分布"
            subtitle={industries.length === 1
              ? "⚠️ 全部集中在一个行业，建议增加持仓数或换 Ensemble 策略"
              : `${industries.length} 个行业`} />
          <CardBody>
            <div className="space-y-2">
              {industries.map(([ind, n]) => (
                <div key={ind} className="flex items-center gap-2 text-xs">
                  <span className="w-24 text-muted">{ind}</span>
                  <div className="flex-1 bg-panel-2 rounded h-2 overflow-hidden">
                    <div className="bg-accent h-full" style={{ width: `${(n / buyPlans.length) * 100}%` }} />
                  </div>
                  <span className="w-10 text-right font-mono">{n}</span>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      <Card className="border-down/30">
        <CardHeader title="实盘前必读" />
        <CardBody>
          <ol className="text-sm text-fg/90 space-y-2 leading-relaxed list-decimal pl-5">
            <li>
              <strong className="text-down">高于上限的票今天不要追</strong>。
              如果开盘超过 ¥X.XX，跳过这只，可能错过；这只比追错更便宜。
            </li>
            <li>
              <strong className="text-fg">"跳过"的票</strong>说明一手已超目标金额。
              不需要硬买——市场上还有 50 只候选。
            </li>
            <li>
              如果行业分布高度集中（⚠️ 横幅），考虑换 Ensemble 策略或加大持仓数。
              集中持有一个行业 = 押注那一个行业涨。
            </li>
            <li>
              本表是 paper-trading 建议。实盘前先用模拟账号跟 1-2 月验证手感。
            </li>
          </ol>
        </CardBody>
      </Card>
    </div>
  );
}

function StatusPill({ status }: { status: Plan["status"] }) {
  switch (status) {
    case "buy":
      return <span className="text-[11px] font-medium text-up bg-up/10 border border-up/30 rounded px-1.5 py-0.5">可买</span>;
    case "expensive":
      return <span className="text-[11px] font-medium text-down bg-down/10 border border-down/30 rounded px-1.5 py-0.5">一手超额跳过</span>;
    case "no_price":
      return <span className="text-[11px] font-medium text-muted bg-panel-2 border border-border rounded px-1.5 py-0.5">无价</span>;
    case "skipped":
      return <span className="text-[11px] font-medium text-muted bg-panel-2 border border-border rounded px-1.5 py-0.5">跳过</span>;
  }
}

function SummaryCard({
  label, value, accent, tone, hint,
}: { label: string; value: string; accent?: boolean; tone?: "down" | "up"; hint?: string }) {
  const colorCls = tone === "down" ? "text-down" : tone === "up" ? "text-up" : accent ? "text-accent" : "text-fg";
  return (
    <div className="bg-panel border border-border rounded-md p-3">
      <div className="text-xs text-muted">{label}</div>
      <div className={`text-lg font-mono mt-1 ${colorCls}`}>{value}</div>
      {hint && <div className="text-[10px] text-muted mt-0.5">{hint}</div>}
    </div>
  );
}
