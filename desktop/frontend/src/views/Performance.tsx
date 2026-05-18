import { useEffect, useMemo, useState } from "react";
import { api, type PerformanceRow } from "@/api";
import { Card, CardBody, CardHeader, Pill } from "@/components/Card";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { useThemeColors } from "@/hooks/useThemeColors";

type Series = "csi300" | "path_a" | "path_d" | "ensemble";

export function PerformanceView({ refreshKey }: { refreshKey: number }) {
  const [rows, setRows] = useState<PerformanceRow[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tc = useThemeColors();

  useEffect(() => {
    setError(null);
    setRows(null);
    api
      .performanceTimeseries()
      .then((r) => {
        setRows(r.rows);
        setMessage(r.message ?? null);
      })
      .catch((e) => setError(String(e)));
  }, [refreshKey]);

  const chartData = useMemo(() => {
    if (!rows) return [];
    let cumA = 1, cumD = 1, cumE = 1, cumC = 1;
    return rows.map((r) => {
      if (r.csi300_cum_ret != null) cumC *= 1 + r.csi300_cum_ret;
      if (r.path_a_cum_ret != null) cumA *= 1 + r.path_a_cum_ret;
      if (r.path_d_cum_ret != null) cumD *= 1 + r.path_d_cum_ret;
      if (r.ensemble_cum_ret != null) cumE *= 1 + r.ensemble_cum_ret;
      return {
        date: r.eval_date ?? r.prediction_date,
        csi300: (cumC - 1) * 100,
        path_a: (cumA - 1) * 100,
        path_d: (cumD - 1) * 100,
        ensemble: (cumE - 1) * 100,
      };
    });
  }, [rows]);

  const colors: Record<Series, string> = {
    csi300: tc.muted,
    path_a: tc.accent,
    path_d: "#a855f7",
    ensemble: tc.up,
  };

  if (error) return <div className="p-6 text-down text-sm">加载失败：{error}</div>;
  if (!rows) return <div className="p-6 text-muted text-sm">加载中…</div>;

  return (
    <div className="p-6 space-y-6 overflow-auto">
      <div className="flex items-baseline gap-3">
        <h1 className="text-2xl font-semibold text-fg">月度绩效追踪</h1>
        <Pill>{rows.length} 次评估</Pill>
      </div>

      {rows.length === 0 ? (
        <Card>
          <CardBody>
            <div className="text-sm text-muted leading-relaxed">
              {message ?? "尚无月度绩效记录。"}
              <br />
              <span className="text-xs">
                第一次月度更新跑完后，下次（25-45 天后）跑会自动评估上一期持仓 vs CSI300，
                并把结果追加到 <code className="font-mono bg-panel-2 px-1 rounded">paper_trades/ensemble_evaluation.csv</code>。
              </span>
            </div>
          </CardBody>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader title="累计收益曲线" subtitle="月末再投资基础" />
            <CardBody>
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                    <CartesianGrid stroke={tc.border} strokeDasharray="3 3" />
                    <XAxis dataKey="date" stroke={tc.muted} fontSize={11} />
                    <YAxis stroke={tc.muted} fontSize={11} tickFormatter={(v) => `${v.toFixed(1)}%`} />
                    <Tooltip
                      contentStyle={{ background: tc.panel, border: `1px solid ${tc.border}`, borderRadius: 6, fontSize: 12 }}
                      labelStyle={{ color: tc.fg }}
                      formatter={(v) => (typeof v === "number" ? `${v.toFixed(2)}%` : `${v}`)}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="csi300" name="CSI300" stroke={colors.csi300} dot={false} strokeWidth={2} />
                    <Line type="monotone" dataKey="path_a" name="Path A" stroke={colors.path_a} dot={false} strokeWidth={2} />
                    <Line type="monotone" dataKey="path_d" name="Path D" stroke={colors.path_d} dot={false} strokeWidth={2} />
                    <Line type="monotone" dataKey="ensemble" name="Ensemble" stroke={colors.ensemble} dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="月度评估" subtitle="持仓 N+1 月 vs CSI300" />
            <CardBody>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted text-xs border-b border-border">
                    <th className="text-left py-2 font-normal">预测日</th>
                    <th className="text-left py-2 font-normal">评估日</th>
                    <th className="text-right py-2 font-normal">CSI300</th>
                    <th className="text-right py-2 font-normal">Path A 超额</th>
                    <th className="text-right py-2 font-normal">Path D 超额</th>
                    <th className="text-right py-2 font-normal">Ensemble 超额</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className="border-b border-border/30 hover:bg-panel-2/50">
                      <td className="py-2 font-mono text-xs">{r.prediction_date}</td>
                      <td className="py-2 font-mono text-xs">{r.eval_date ?? "—"}</td>
                      <td className="py-2 text-right font-mono">
                        {r.csi300_cum_ret != null
                          ? `${(r.csi300_cum_ret * 100).toFixed(2)}%`
                          : "—"}
                      </td>
                      {(["path_a_excess", "path_d_excess", "ensemble_excess"] as const).map((k) => {
                        const v = r[k];
                        return (
                          <td
                            key={k}
                            className={`py-2 text-right font-mono ${
                              v == null ? "" : v >= 0 ? "text-up" : "text-down"
                            }`}
                          >
                            {v == null
                              ? "—"
                              : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardBody>
          </Card>
        </>
      )}
    </div>
  );
}
