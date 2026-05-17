import { useEffect, useMemo, useState } from "react";
import { api, type EtfComparison } from "@/api";
import { Card, CardBody, CardHeader, Pill } from "@/components/Card";
import { fmtMoney, useProfile } from "@/profile";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";

export function BenchmarkView({ refreshKey }: { refreshKey: number }) {
  const [profile] = useProfile();
  const [data, setData] = useState<EtfComparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(252);

  useEffect(() => {
    setError(null);
    setData(null);
    api.etfComparison(days)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [refreshKey, days]);

  const chartData = useMemo(() => {
    if (!data?.csi300_index) return [];
    return data.csi300_index.map((r) => ({
      date: r.date,
      csi300: r.cum_ret * 100,
    }));
  }, [data]);

  const finalReturn = chartData.length > 0 ? chartData[chartData.length - 1].csi300 / 100 : 0;
  const annualized = Math.pow(1 + finalReturn, 252 / Math.max(chartData.length, 1)) - 1;
  const invested = profile.capital * (1 - profile.cashReservePct);
  const wouldHave = invested * (1 + finalReturn);

  if (error) return <div className="p-6 text-down text-sm">加载失败：{error}</div>;

  return (
    <div className="p-6 space-y-6 overflow-auto">
      <div className="flex items-baseline gap-3">
        <h1 className="text-2xl font-semibold text-fg">vs 沪深300 基准</h1>
        <Pill>"如果你不做这套，直接买 ETF 会怎样"</Pill>
      </div>

      <div className="flex items-center gap-2 text-xs">
        <span className="text-muted">时间窗口：</span>
        {[63, 126, 252, 504].map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setDays(d)}
            className={`px-2.5 py-1 rounded-md border transition ${
              days === d
                ? "bg-accent/15 text-accent border-accent/40"
                : "bg-panel border-border text-muted hover:text-fg"
            }`}
          >
            {d === 63 ? "3月" : d === 126 ? "6月" : d === 252 ? "1年" : "2年"}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardHeader title="期间累计收益" subtitle="CSI300 指数（510300 ETF 跟踪标的）" />
          <CardBody>
            <div className={`text-3xl font-mono ${finalReturn >= 0 ? "text-up" : "text-down"}`}>
              {finalReturn >= 0 ? "+" : ""}{(finalReturn * 100).toFixed(2)}%
            </div>
            <div className="text-xs text-muted mt-2">
              年化 {(annualized * 100).toFixed(2)}%（{chartData.length} 个交易日）
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="如果用你的本金买 ETF" />
          <CardBody>
            {profile.capital === 0 ? (
              <div className="text-sm text-muted">未设置本金</div>
            ) : (
              <div>
                <div className="text-3xl font-mono text-accent">
                  {fmtMoney(wouldHave)}
                </div>
                <div className="text-xs text-muted mt-2">
                  期间盈亏 {finalReturn >= 0 ? "+" : ""}{fmtMoney(invested * finalReturn)}
                </div>
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="ETF 摩擦成本" />
          <CardBody>
            <div className="text-3xl font-mono text-muted">
              ~{((data?.etf_drag_assumption_annual ?? 0.005) * 100).toFixed(2)}%/年
            </div>
            <div className="text-xs text-muted mt-2">
              管理费 + 跟踪误差。指数图未扣除，实际收益略低。
            </div>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="CSI300 累计收益曲线"
          subtitle="所有 paper-trade 业绩都要跟它对比，跑赢才算真本事" />
        <CardBody>
          {chartData.length === 0 ? (
            <div className="text-sm text-muted">无数据</div>
          ) : (
            <div className="h-80 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                  <CartesianGrid stroke="#232a3a" strokeDasharray="3 3" />
                  <XAxis dataKey="date" stroke="#94a3b8" fontSize={11}
                    tickFormatter={(d: string) => d.slice(5)} />
                  <YAxis stroke="#94a3b8" fontSize={11}
                    tickFormatter={(v) => `${v.toFixed(1)}%`} />
                  <Tooltip
                    contentStyle={{ background: "#131822", border: "1px solid #232a3a", borderRadius: 6, fontSize: 12 }}
                    labelStyle={{ color: "#e5e7eb" }}
                    formatter={(v) => (typeof v === "number" ? `${v.toFixed(2)}%` : `${v}`)}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="csi300" name="CSI300 指数"
                    stroke="#94a3b8" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="给新投资人的诚实建议" />
        <CardBody>
          <div className="text-sm text-fg/90 space-y-2 leading-relaxed">
            <p>
              <strong className="text-fg">如果上图 1 年期 CSI300 涨了 20%+，</strong>
              那说明同期所有 buy-and-hold ETF 投资者都赚了 20%。
              我们这套 paper-trade 系统的目标是**长期跑赢这条灰线 3-8 个百分点**——
              不是给你"翻倍致富"。
            </p>
            <p>
              <strong className="text-fg">如果上图是负的，</strong>
              那是熊市期，我们的反转/行业模型在熊市里历史上**没有数据**支撑其表现。
              这种环境下减仓 + 等月度评估出正信号才下注是稳妥做法。
            </p>
            <p>
              <strong className="text-fg">最常见的失败模式：</strong>
              牛市跟模型半年看到 +30%，自以为掌握了 alpha，加大本金，结果熊市跟着回吐 30%+。
              对策：**只在 paper-trading 评估积累到 ≥ 6 个月、且最大回撤 ≤ 你能承受的水平后，才考虑实盘**。
            </p>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
