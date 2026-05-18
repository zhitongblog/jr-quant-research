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

      {detail.earnings_forecast && <EarningsForecastBanner ef={detail.earnings_forecast} />}

      <VerdictCard detail={detail} />

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

      {/* New: Price Summary + Valuation + Fundamentals row */}
      <div className="grid grid-cols-3 gap-4">
        <PriceSummaryCard summary={detail.price_summary} />
        <ValuationCard val={detail.valuation} />
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

// -------- Verdict Card (傻瓜评分卡) --------

type Light = "green" | "yellow" | "red" | "gray";

function VerdictCard({ detail }: { detail: import("@/api").StockDetail }) {
  // ---------- 1. 基本面 ----------
  const fund = detail.fundamentals;
  let fundLight: Light = "gray";
  let fundReason = "无数据";
  if (fund) {
    const roe = fund.roe_weighted ?? fund.roe;
    const yoy = fund.earnings_yoy;
    const debt = fund.debt_ratio;
    let score = 0;
    const notes: string[] = [];
    if (roe != null) {
      if (roe >= 10) { score += 1; notes.push(`ROE ${roe.toFixed(1)}% 健康`); }
      else if (roe >= 5) { notes.push(`ROE ${roe.toFixed(1)}% 一般`); }
      else { score -= 1; notes.push(`ROE ${roe.toFixed(1)}% 偏低`); }
    }
    if (yoy != null) {
      if (yoy >= 20) { score += 1; notes.push(`净利同比 +${yoy.toFixed(0)}% 强劲`); }
      else if (yoy >= 0) { notes.push(`净利同比 +${yoy.toFixed(0)}% 微增`); }
      else if (yoy >= -20) { score -= 1; notes.push(`净利同比 ${yoy.toFixed(0)}% 下滑`); }
      else { score -= 2; notes.push(`净利同比 ${yoy.toFixed(0)}% 大幅下滑`); }
    }
    if (debt != null) {
      if (debt < 50) { score += 1; notes.push(`负债率 ${debt.toFixed(0)}% 低`); }
      else if (debt < 70) { notes.push(`负债率 ${debt.toFixed(0)}% 适中`); }
      else if (debt < 85) { score -= 1; notes.push(`负债率 ${debt.toFixed(0)}% 偏高`); }
      else { score -= 1; notes.push(`负债率 ${debt.toFixed(0)}% 很高`); }
    }
    fundLight = score >= 2 ? "green" : score >= 0 ? "yellow" : "red";
    fundReason = notes.join("·") || "数据不足";
  }

  // ---------- 2. 估值 (优先用 PE 5y 分位；fallback 到 52 周位置) ----------
  let valLight: Light = "yellow";
  let valReason = "数据不足";
  const pePct = detail.valuation?.pe_pct_5y;
  if (pePct != null) {
    const p = pePct * 100;
    if (p < 25) { valLight = "green"; valReason = `PE 处于 5 年 ${p.toFixed(0)} 百分位（便宜，过去 5 年里 ${(100-p).toFixed(0)}% 时间比现在贵）`; }
    else if (p < 50) { valLight = "green"; valReason = `PE 处于 5 年 ${p.toFixed(0)} 百分位（中下，偏便宜）`; }
    else if (p < 75) { valLight = "yellow"; valReason = `PE 处于 5 年 ${p.toFixed(0)} 百分位（中性）`; }
    else if (p < 90) { valLight = "red"; valReason = `PE 处于 5 年 ${p.toFixed(0)} 百分位（偏贵）`; }
    else { valLight = "red"; valReason = `PE 处于 5 年 ${p.toFixed(0)} 百分位（极贵，过去 5 年里 ${(100-p).toFixed(0)}% 时间都比现在便宜）`; }
  } else {
    const pos = detail.price_summary?.week_52_position_pct;
    if (pos != null) {
      const pct = pos * 100;
      if (pct < 20) { valLight = "green"; valReason = `52 周位置 ${pct.toFixed(0)}%（低位）`; }
      else if (pct < 50) { valLight = "green"; valReason = `52 周位置 ${pct.toFixed(0)}%（中低位）`; }
      else if (pct < 80) { valLight = "yellow"; valReason = `52 周位置 ${pct.toFixed(0)}%`; }
      else { valLight = "red"; valReason = `52 周位置 ${pct.toFixed(0)}%（高位）`; }
    }
  }

  // ---------- 3. 技术面 ----------
  let techLight: Light = "gray";
  let techReason = "无数据";
  const maStat = detail.price_summary?.ma_status;
  const volRatio = detail.price_summary?.volume_ratio_5d;
  if (maStat) {
    if (maStat === "bullish") { techLight = "green"; techReason = "多头排列（MA5>10>20>60，趋势向上）"; }
    else if (maStat === "bearish") { techLight = "red"; techReason = "空头排列（MA 单调向下，趋势走弱）"; }
    else { techLight = "yellow"; techReason = "震荡（均线交错）"; }
    if (volRatio != null && volRatio > 2) techReason += `· 今日放量 ${volRatio.toFixed(1)}x 🔥`;
    if (volRatio != null && volRatio < 0.5) techReason += `· 今日缩量 ${volRatio.toFixed(1)}x`;
  }

  // ---------- 4. AI 推荐 ----------
  const aiIn = detail.in_portfolio;
  let aiLight: Light = "gray";
  let aiReason = "本月模型未推荐";
  if (aiIn) {
    if (aiIn.ensemble) { aiLight = "green"; aiReason = "本月 Ensemble 综合推荐持仓"; }
    else if (aiIn.path_a && aiIn.path_d) { aiLight = "green"; aiReason = "Path A + Path D 双重推荐"; }
    else if (aiIn.path_a) { aiLight = "yellow"; aiReason = "Path A (量价模型) 单边推荐"; }
    else if (aiIn.path_d) { aiLight = "yellow"; aiReason = "Path D (LLM 行业) 单边推荐"; }
  }

  // ---------- 综合判断 ----------
  const lights = [fundLight, valLight, techLight, aiLight];
  const greens = lights.filter((l) => l === "green").length;
  const reds = lights.filter((l) => l === "red").length;
  let overall: { tone: Light; label: string; advice: string };
  if (greens >= 3 && reds === 0) {
    overall = { tone: "green", label: "✅ 综合较优", advice: "基本面、技术面、AI 推荐都偏正面。可按推荐价位买入。" };
  } else if (reds >= 2) {
    overall = { tone: "red", label: "🚨 综合偏弱", advice: "多项警示信号。如果纯跟单（不查个股）建议跳过这只，从 peers 里挑替代。" };
  } else if (greens >= 2 && reds === 0) {
    overall = { tone: "green", label: "🟢 可关注", advice: "整体偏正面，可按推荐价位试探性买入小仓位。" };
  } else if (reds === 1) {
    overall = { tone: "yellow", label: "⚠️ 谨慎", advice: "有 1 项警示信号。建议买入仓位减半，或等回调到下限再考虑。" };
  } else {
    overall = { tone: "yellow", label: "🟡 中性", advice: "信号不强不弱，按你的整体策略执行即可。" };
  }

  const toneClass = (l: Light) =>
    l === "green" ? "bg-up/10 border-up/40 text-up" :
    l === "red" ? "bg-down/10 border-down/40 text-down" :
    l === "yellow" ? "bg-yellow-500/10 border-yellow-500/40 text-yellow-400" :
    "bg-panel-2 border-border text-muted";

  const dot = (l: Light) =>
    l === "green" ? "🟢" : l === "red" ? "🔴" : l === "yellow" ? "🟡" : "⚪";

  return (
    <Card className={`border-2 ${
      overall.tone === "green" ? "border-up/40" :
      overall.tone === "red" ? "border-down/40" :
      "border-yellow-500/40"
    }`}>
      <CardHeader
        title={`一句话判断：${overall.label}`}
        subtitle={overall.advice}
      />
      <CardBody>
        <div className="grid grid-cols-4 gap-3">
          <VerdictTile light={fundLight} icon={dot(fundLight)} label="基本面" reason={fundReason} tone={toneClass(fundLight)} />
          <VerdictTile light={valLight} icon={dot(valLight)} label="估值/位置" reason={valReason} tone={toneClass(valLight)} />
          <VerdictTile light={techLight} icon={dot(techLight)} label="技术面" reason={techReason} tone={toneClass(techLight)} />
          <VerdictTile light={aiLight} icon={dot(aiLight)} label="AI 推荐" reason={aiReason} tone={toneClass(aiLight)} />
        </div>
        <div className="text-[10px] text-muted leading-relaxed mt-3">
          🟢 = 利好；🟡 = 中性；🔴 = 警示；⚪ = 数据不足。<br />
          ⚠️ 评分仅基于公开数据 + 量化规则，<strong className="text-fg">不构成投资建议</strong>。极端事件、突发利空、政策变化不在此评分覆盖范围内。
        </div>
      </CardBody>
    </Card>
  );
}

// -------- Earnings Forecast Banner --------

function EarningsForecastBanner({ ef }: { ef: import("@/api").EarningsForecast }) {
  const p = ef.primary;
  const isGood = p.type.includes("增") || p.type.includes("续盈") || (p.change_pct != null && p.change_pct > 0);
  const isBad = p.type.includes("减") || p.type.includes("亏") || p.type.includes("续亏") || (p.change_pct != null && p.change_pct < -10);
  const tone = isGood ? "up" : isBad ? "down" : "accent";
  const toneBg = isGood ? "border-up/40 bg-up/5" : isBad ? "border-down/40 bg-down/5" : "border-accent/40 bg-accent/5";
  const icon = isGood ? "📈" : isBad ? "📉" : "📊";
  return (
    <div className={`border-2 rounded-md p-3 ${toneBg}`}>
      <div className="flex items-baseline gap-2 mb-1">
        <span className="text-xl">{icon}</span>
        <Pill tone={tone as "up" | "down" | "accent"}>{p.type || "预告"}</Pill>
        <span className="text-sm text-fg font-medium">{p.metric}</span>
        <span className="text-xs text-muted">报告期 {p.report_period.slice(0,4)}-Q{Math.ceil(parseInt(p.report_period.slice(4,6))/3)}</span>
        {p.change_pct != null && (
          <span className={`ml-auto font-mono text-sm ${
            p.change_pct >= 0 ? "text-up" : "text-down"
          }`}>
            同比 {p.change_pct >= 0 ? "+" : ""}{p.change_pct.toFixed(1)}%
          </span>
        )}
      </div>
      <div className="text-xs text-fg/85 leading-relaxed">
        {p.description}
      </div>
      {ef.all_metrics.length > 1 && (
        <details className="mt-2 text-xs text-muted">
          <summary className="cursor-pointer hover:text-fg">其他 {ef.all_metrics.length - 1} 项预告</summary>
          <ul className="mt-1 space-y-1 pl-4">
            {ef.all_metrics.slice(1).map((m, i) => (
              <li key={i}>
                <span className="text-fg">{m.metric}</span>
                {m.change_pct != null && (
                  <span className={`ml-2 font-mono ${m.change_pct >= 0 ? "text-up" : "text-down"}`}>
                    {m.change_pct >= 0 ? "+" : ""}{m.change_pct.toFixed(1)}%
                  </span>
                )}
                <span className="text-muted ml-2">{m.description.slice(0, 60)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

// -------- Valuation Card --------

function ValuationCard({ val }: { val: import("@/api").ValuationSummary | null }) {
  if (!val) {
    return (
      <Card>
        <CardHeader title="估值 (PE/PB)" />
        <CardBody>
          <div className="text-xs text-muted leading-relaxed">
            尚未拉历史估值数据。<br/>
            运行 <code className="font-mono bg-panel-2 px-1 rounded">scripts/pull_valuation_earnings.py</code> 后会出现 PE/PB 历史百分位。
          </div>
        </CardBody>
      </Card>
    );
  }
  const fmtPE = (v: number | null) => v == null ? "—" : v < 0 ? "亏损" : v.toFixed(1);
  const pePctNum = val.pe_pct_5y;
  const pbPctNum = val.pb_pct_5y;

  const pctLabel = (p: number) => {
    const v = p * 100;
    if (v < 25) return { tone: "up", label: `${v.toFixed(0)} 分位 · 偏便宜` };
    if (v < 50) return { tone: "up", label: `${v.toFixed(0)} 分位 · 中下` };
    if (v < 75) return { tone: "neutral", label: `${v.toFixed(0)} 分位 · 中性` };
    if (v < 90) return { tone: "down", label: `${v.toFixed(0)} 分位 · 偏贵` };
    return { tone: "down", label: `${v.toFixed(0)} 分位 · 极贵` };
  };

  return (
    <Card>
      <CardHeader title="估值 (PE/PB)" subtitle={`${val.n_years_history.toFixed(1)} 年历史 · 截止 ${val.as_of}`} />
      <CardBody className="space-y-3">
        <ValRow label="PE (TTM)" value={fmtPE(val.pe_ttm)} pct={pePctNum} pctLabel={pePctNum != null ? pctLabel(pePctNum) : null} />
        <ValRow label="市净率 PB" value={fmtPE(val.pb)} pct={pbPctNum} pctLabel={pbPctNum != null ? pctLabel(pbPctNum) : null} />
        {val.ps != null && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted">市销率 PS</span>
            <span className="font-mono text-fg">{val.ps.toFixed(2)}</span>
          </div>
        )}
        {val.market_cap != null && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted">总市值</span>
            <span className="font-mono text-fg">
              {val.market_cap >= 1e10
                ? `${(val.market_cap / 1e8).toFixed(0)} 亿`
                : `${(val.market_cap / 1e8).toFixed(2)} 亿`}
            </span>
          </div>
        )}
        <div className="text-[10px] text-muted leading-relaxed pt-2 border-t border-border/30">
          百分位 = 当前 PE/PB 在过去 5 年中的相对位置。<br />
          数值越低 = 历史相对越便宜；数值越高 = 历史相对越贵。
        </div>
      </CardBody>
    </Card>
  );
}

function ValRow({
  label, value, pct, pctLabel,
}: { label: string; value: string; pct: number | null | undefined; pctLabel: { tone: string; label: string } | null }) {
  const toneClass = pctLabel?.tone === "up" ? "text-up bg-up/10 border-up/30"
    : pctLabel?.tone === "down" ? "text-down bg-down/10 border-down/30"
    : "text-muted bg-panel-2 border-border";
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted">{label}</span>
        <span className="font-mono text-base text-fg">{value}</span>
      </div>
      {pct != null && pctLabel && (
        <div className="mt-1.5">
          <div className="h-1.5 bg-panel-2 rounded overflow-hidden relative">
            <div className="absolute h-full w-full bg-gradient-to-r from-up/30 via-yellow-500/30 to-down/30" />
            <div className="absolute h-full w-1 bg-accent" style={{ left: `${pct * 100}%` }} />
          </div>
          <div className={`mt-1 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono border ${toneClass}`}>
            {pctLabel.label}
          </div>
        </div>
      )}
    </div>
  );
}

function VerdictTile({ icon, label, reason, tone }: { light: Light; icon: string; label: string; reason: string; tone: string }) {
  return (
    <div className={`rounded-md border p-3 ${tone}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xl">{icon}</span>
        <span className="text-sm font-medium">{label}</span>
      </div>
      <div className="text-[11px] leading-relaxed opacity-90">{reason}</div>
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
