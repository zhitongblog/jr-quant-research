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
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted text-xs border-b border-border">
                  <th className="text-left py-2 font-normal">代码</th>
                  <th className="text-left py-2 font-normal">名称</th>
                  <th className="text-right py-2 font-normal">收盘</th>
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
                    <td className="py-2 font-mono text-xs">{p.symbol}</td>
                    <td className="py-2 text-fg">{p.name}</td>
                    <td className="py-2 text-right font-mono">¥{p.close.toFixed(2)}</td>
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
