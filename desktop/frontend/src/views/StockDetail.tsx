import { useEffect, useMemo, useState } from "react";
import { api, type StockDetail, type StockPrices } from "@/api";
import { Card, CardBody, CardHeader, Pill } from "@/components/Card";
import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceDot,
} from "recharts";

const FACTOR_LABEL: Record<string, string> = {
  limit_up_reversal_20d: "涨停反转 (20日)",
  price_volume_divergence: "量价背离",
  amihud_illiquidity_20d: "Amihud 流动性 (20日)",
};

function fmt(v: number | null | undefined, dp = 4) {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toFixed(dp);
}
function fmtPct(v: number | null | undefined) {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
}

export function StockDetailView({
  symbol,
  onBack,
  onSelectSymbol,
}: {
  symbol: string;
  onBack: () => void;
  onSelectSymbol: (s: string) => void;
}) {
  const [detail, setDetail] = useState<StockDetail | null>(null);
  const [prices, setPrices] = useState<StockPrices | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    setDetail(null);
    setPrices(null);
    Promise.all([api.stockDetail(symbol), api.stockPrices(symbol, 120)])
      .then(([d, p]) => {
        setDetail(d);
        setPrices(p);
      })
      .catch((e) => setError(String(e)));
  }, [symbol]);

  const limitUpDays = useMemo(
    () => prices?.rows.filter((r) => r.limit_up) ?? [],
    [prices],
  );

  if (error) {
    return (
      <div className="p-6 space-y-4">
        <button type="button" onClick={onBack} className="text-sm text-accent hover:underline">
          ← 返回
        </button>
        <div className="text-down text-sm">加载失败：{error}</div>
      </div>
    );
  }
  if (!detail || !prices) {
    return <div className="p-6 text-muted text-sm">加载中…</div>;
  }

  const info = detail.info;
  return (
    <div className="p-6 space-y-6 overflow-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-3">
          <button type="button" onClick={onBack} className="text-sm text-accent hover:underline">
            ← 返回
          </button>
          <h1 className="text-2xl font-semibold text-fg">{info.name}</h1>
          <Pill>{info.symbol}</Pill>
          <Pill tone="accent">{info.sw1_code} {info.sw1_name}</Pill>
          {detail.factors_latest && (
            <span className="text-muted text-sm font-mono">
              最新 {detail.factors_latest.as_of} · ¥{detail.factors_latest.close.toFixed(2)}
              {detail.factors_latest.ret_1d != null && (
                <span className={detail.factors_latest.ret_1d >= 0 ? " text-up" : " text-down"}>
                  {" "}{fmtPct(detail.factors_latest.ret_1d)}
                </span>
              )}
            </span>
          )}
        </div>
      </div>

      <Card>
        <CardHeader
          title="K线 / 收盘价 + 成交量"
          subtitle={`近 ${prices.rows.length} 个交易日，红点 = 涨停 (≥9.5%)`}
        />
        <CardBody>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={prices.rows}
                margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
              >
                <CartesianGrid stroke="#232a3a" strokeDasharray="3 3" />
                <XAxis dataKey="date" stroke="#94a3b8" fontSize={11}
                  tickFormatter={(d) => d.slice(5)} />
                <YAxis yAxisId="price" stroke="#94a3b8" fontSize={11} domain={["dataMin", "dataMax"]} />
                <YAxis yAxisId="vol" orientation="right" stroke="#94a3b8" fontSize={11}
                  tickFormatter={(v) => `${(v / 1e7).toFixed(0)}M`} />
                <Tooltip
                  contentStyle={{ background: "#131822", border: "1px solid #232a3a", borderRadius: 6, fontSize: 12 }}
                  labelStyle={{ color: "#e5e7eb" }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar yAxisId="vol" dataKey="volume" name="成交量" fill="#3a4255" />
                <Line yAxisId="price" type="monotone" dataKey="close" name="收盘价" stroke="#38bdf8" dot={false} strokeWidth={2} />
                {limitUpDays.map((d) => (
                  <ReferenceDot
                    key={d.date}
                    yAxisId="price"
                    x={d.date}
                    y={d.close}
                    r={4}
                    fill="#ef4444"
                    stroke="#ef4444"
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardBody>
      </Card>

      {/* New: Price Summary + Fundamentals row */}
      <div className="grid grid-cols-2 gap-4">
        <PriceSummaryCard summary={detail.price_summary} />
        <FundamentalsCard fund={detail.fundamentals} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader title="当前因子值 + 行业内排名"
            subtitle={`同行业 ${detail.industry_size} 只成分股`} />
          <CardBody>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted text-xs border-b border-border">
                  <th className="text-left py-2 font-normal">因子</th>
                  <th className="text-right py-2 font-normal">原始值</th>
                  <th className="text-right py-2 font-normal">行业均值</th>
                  <th className="text-right py-2 font-normal">行业相对</th>
                  <th className="text-right py-2 font-normal">排名</th>
                </tr>
              </thead>
              <tbody>
                {(["limit_up_reversal_20d", "price_volume_divergence", "amihud_illiquidity_20d"] as const).map((k) => {
                  const v = detail.factors_latest?.[k];
                  const rk = detail.industry_rank[k];
                  const rel = detail.industry_relative[k];
                  return (
                    <tr key={k} className="border-b border-border/30">
                      <td className="py-2 text-fg">{FACTOR_LABEL[k]}</td>
                      <td className="py-2 text-right font-mono">{fmt(v ?? null)}</td>
                      <td className="py-2 text-right font-mono text-muted">{fmt(rk?.industry_mean)}</td>
                      <td className={`py-2 text-right font-mono ${
                        rel == null ? "" : rel >= 0 ? "text-up" : "text-down"
                      }`}>
                        {rel == null ? "—" : `${rel >= 0 ? "+" : ""}${rel.toFixed(4)}`}
                      </td>
                      <td className="py-2 text-right font-mono">
                        {rk?.rank ? `${rk.rank}/${rk.total}` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="mt-3 text-xs text-muted leading-relaxed">
              <strong className="text-fg">解读</strong>：行业相对 = 个股因子值 − 同行业均值。排名 1 = 同行业最高。
              "涨停反转"越负越好（限定为 -0.10 ~ -0.095，越接近 -0.10 表示近期涨停越多）；
              "量价背离"和 "Amihud 流动性"由 LGB 综合判断，行业相对值才是关键。
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="同行业 top peers"
            subtitle="按因子综合 z-score 排序（点击切换查看）" />
          <CardBody>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted border-b border-border">
                  <th className="text-left py-2 font-normal">名称</th>
                  <th className="text-right py-2 font-normal">收盘</th>
                  <th className="text-right py-2 font-normal">ROE</th>
                  <th className="text-right py-2 font-normal">净利同比</th>
                  <th className="text-right py-2 font-normal">负债率</th>
                  <th className="text-right py-2 font-normal">综合</th>
                </tr>
              </thead>
              <tbody>
                {detail.peers.map((p) => (
                  <tr
                    key={p.qlib_symbol}
                    onClick={() => onSelectSymbol(p.qlib_symbol)}
                    className={`border-b border-border/30 cursor-pointer hover:bg-panel-2/50 ${
                      p.qlib_symbol === `SH${info.symbol}` || p.qlib_symbol === `SZ${info.symbol}` ? "bg-accent/5" : ""
                    }`}
                  >
                    <td className="py-2">
                      <div className="font-mono text-muted">{p.symbol}</div>
                      <div className="text-fg">{p.name}</div>
                    </td>
                    <td className="py-2 text-right font-mono">¥{p.close.toFixed(2)}</td>
                    <td className="py-2 text-right font-mono">{p.roe_weighted != null ? `${p.roe_weighted.toFixed(1)}%` : "—"}</td>
                    <td className={`py-2 text-right font-mono ${
                      p.earnings_yoy == null ? "" : p.earnings_yoy >= 0 ? "text-up" : "text-down"
                    }`}>
                      {p.earnings_yoy != null ? `${p.earnings_yoy >= 0 ? "+" : ""}${p.earnings_yoy.toFixed(1)}%` : "—"}
                    </td>
                    <td className="py-2 text-right font-mono">{p.debt_ratio != null ? `${p.debt_ratio.toFixed(0)}%` : "—"}</td>
                    <td className="py-2 text-right font-mono text-accent">{p.combo.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

// -------- Price Summary Card --------

function PriceSummaryCard({ summary }: { summary: import("@/api").PriceSummary | null }) {
  if (!summary) {
    return (
      <Card>
        <CardHeader title="价格位置 + 均线" />
        <CardBody>
          <div className="text-xs text-muted">数据不足</div>
        </CardBody>
      </Card>
    );
  }
  const posPct = summary.week_52_position_pct * 100;
  const maTone = summary.ma_status === "bullish" ? "up" :
    summary.ma_status === "bearish" ? "down" : "neutral";
  const maLabel = summary.ma_status === "bullish" ? "多头排列" :
    summary.ma_status === "bearish" ? "空头排列" : "震荡";

  return (
    <Card>
      <CardHeader title="价格位置 + 均线" subtitle={`最新 ${summary.as_of}`}
        right={<Pill tone={maTone as "up" | "down" | "neutral"}>{maLabel}</Pill>} />
      <CardBody className="space-y-3">
        <div>
          <div className="flex justify-between text-xs text-muted mb-1">
            <span>52 周低 ¥{summary.week_52_low.toFixed(2)}</span>
            <span>当前 <span className="text-fg font-mono">¥{summary.close.toFixed(2)}</span> ({posPct.toFixed(0)}%)</span>
            <span>52 周高 ¥{summary.week_52_high.toFixed(2)}</span>
          </div>
          <div className="relative h-2 bg-panel-2 rounded overflow-hidden">
            <div className="absolute h-full bg-gradient-to-r from-down/30 via-muted/30 to-up/30 w-full" />
            <div className="absolute h-full w-1 bg-accent" style={{ left: `${Math.min(100, Math.max(0, posPct))}%` }} />
          </div>
          <div className="text-[10px] text-muted mt-1">
            {posPct < 25 ? "靠近 52 周底部，可能超跌或基本面恶化" :
             posPct > 75 ? "接近 52 周顶部，可能高估或动量强势" :
             "位置中性"}
          </div>
        </div>

        <div>
          <div className="text-xs text-muted mb-1">均线（与当前价对比）</div>
          <div className="grid grid-cols-4 gap-1 text-xs">
            {([5, 10, 20, 60] as const).map((w) => {
              const v = summary[`ma${w}` as const];
              if (v == null) return <div key={w} className="bg-panel-2 rounded p-1.5 text-center text-muted">MA{w} —</div>;
              const diff = (summary.close - v) / v;
              return (
                <div key={w} className="bg-panel-2 rounded p-1.5 text-center">
                  <div className="text-muted text-[10px]">MA{w}</div>
                  <div className="font-mono text-fg">¥{v.toFixed(2)}</div>
                  <div className={`text-[10px] ${diff >= 0 ? "text-up" : "text-down"}`}>
                    {diff >= 0 ? "+" : ""}{(diff * 100).toFixed(1)}%
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {summary.volume_ratio_5d != null && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted">今日量比（vs 5 日均量）</span>
            <span className={`font-mono ${
              summary.volume_ratio_5d > 1.5 ? "text-up" :
              summary.volume_ratio_5d < 0.5 ? "text-down" : "text-fg"
            }`}>
              {summary.volume_ratio_5d.toFixed(2)}x
              {summary.volume_ratio_5d > 2 && " 🔥"}
            </span>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

// -------- Fundamentals Card --------

function FundamentalsCard({ fund }: { fund: import("@/api").Fundamentals | null }) {
  if (!fund) {
    return (
      <Card>
        <CardHeader title="基本面快照" />
        <CardBody>
          <div className="text-xs text-muted">无基本面数据</div>
        </CardBody>
      </Card>
    );
  }

  type FundKey = "roe_weighted" | "earnings_yoy" | "gross_margin" | "op_margin" | "debt_ratio" | "current_ratio";

  const rows: { key: FundKey; label: string; suffix?: string; healthBetter: "high" | "low" | null }[] = [
    { key: "roe_weighted", label: "加权 ROE", suffix: "%", healthBetter: "high" },
    { key: "earnings_yoy", label: "净利润同比", suffix: "%", healthBetter: "high" },
    { key: "gross_margin", label: "销售毛利率", suffix: "%", healthBetter: "high" },
    { key: "op_margin", label: "营业利润率", suffix: "%", healthBetter: "high" },
    { key: "debt_ratio", label: "资产负债率", suffix: "%", healthBetter: "low" },
    { key: "current_ratio", label: "流动比率", suffix: "", healthBetter: "high" },
  ];

  return (
    <Card>
      <CardHeader title="基本面快照" subtitle={`报告期 ${fund.as_of}${fund.prev_as_of ? ` (vs ${fund.prev_as_of})` : ""}`} />
      <CardBody>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-muted border-b border-border">
              <th className="text-left py-1.5 font-normal">指标</th>
              <th className="text-right py-1.5 font-normal">本期</th>
              <th className="text-right py-1.5 font-normal">上期</th>
              <th className="text-right py-1.5 font-normal">变化</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const v = fund[r.key];
              const pv = fund[`prev_${r.key}` as keyof typeof fund] as number | undefined;
              if (v == null) return null;
              const change = (pv != null) ? (v - pv) : null;
              const goodChange = change == null ? null
                : r.healthBetter === "high" ? change >= 0
                : r.healthBetter === "low" ? change <= 0
                : null;
              return (
                <tr key={r.key} className="border-b border-border/30">
                  <td className="py-1.5 text-fg">{r.label}</td>
                  <td className="py-1.5 text-right font-mono">{v.toFixed(2)}{r.suffix}</td>
                  <td className="py-1.5 text-right font-mono text-muted">
                    {pv != null ? `${pv.toFixed(2)}${r.suffix}` : "—"}
                  </td>
                  <td className={`py-1.5 text-right font-mono text-[11px] ${
                    goodChange == null ? "" : goodChange ? "text-up" : "text-down"
                  }`}>
                    {change == null ? "—" :
                      `${change >= 0 ? "+" : ""}${change.toFixed(2)}${r.suffix}`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="text-[10px] text-muted mt-3 leading-relaxed">
          ROE / 净利润同比 / 毛利率：越高越好（绿色 = 改善）<br />
          资产负债率：越低越好（绿色 = 下降）<br />
          数据来自 akshare 财务接口，季频更新。报告期 03/31 = Q1, 06/30 = Q2 等。
        </div>
      </CardBody>
    </Card>
  );
}
