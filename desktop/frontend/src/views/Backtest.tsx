import { useEffect, useState } from "react";
import { api, type BacktestRow } from "@/api";
import { Card, CardBody, CardHeader, Pill } from "@/components/Card";

function fmtPct(v: number | null | undefined) {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(2)}%`;
}
function fmtSharpe(v: number | null | undefined) {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
}

export function BacktestView({ refreshKey }: { refreshKey: number }) {
  const [rows, setRows] = useState<BacktestRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    setRows(null);
    api
      .backtestComparison()
      .then((r) => setRows(r.rows))
      .catch((e) => setError(String(e)));
  }, [refreshKey]);

  if (error) return <div className="p-6 text-down text-sm">加载失败：{error}</div>;
  if (!rows) return <div className="p-6 text-muted text-sm">加载中…</div>;

  // group by version
  const byVer: Record<string, BacktestRow[]> = {};
  for (const r of rows) byVer[r.version] = [...(byVer[r.version] ?? []), r];

  return (
    <div className="p-6 space-y-6 overflow-auto">
      <div className="flex items-baseline gap-3">
        <h1 className="text-2xl font-semibold text-fg">回测成绩对比</h1>
        <Pill>{rows.length} 个策略变体</Pill>
      </div>

      {Object.entries(byVer).map(([ver, items]) => (
        <Card key={ver}>
          <CardHeader
            title={`${ver}: ${ver === "v2" ? "fixed/walk-forward/linear baseline"
              : ver === "v3" ? "industry LGB (Path A)"
              : ver === "v4" ? "industry rotation overlay (Path B)"
              : ver === "v5" ? "industry + fundamentals (Path C)"
              : ""}`}
            right={<Pill>{items.length}</Pill>}
          />
          <CardBody>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted text-xs border-b border-border">
                  <th className="text-left py-2 font-normal">策略</th>
                  <th className="text-right py-2 font-normal">累计净收益</th>
                  <th className="text-right py-2 font-normal">Sharpe</th>
                  <th className="text-right py-2 font-normal">最大回撤</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r, i) => (
                  <tr
                    key={r.name + i}
                    className="border-b border-border/30 hover:bg-panel-2/50"
                  >
                    <td className="py-2 font-mono text-xs">{r.name}</td>
                    <td className={`py-2 text-right font-mono ${
                      (r.cum_net ?? 0) >= 0 ? "text-up" : "text-down"
                    }`}>
                      {fmtPct(r.cum_net)}
                    </td>
                    <td className="py-2 text-right font-mono">{fmtSharpe(r.sharpe)}</td>
                    <td className="py-2 text-right font-mono text-down">
                      {fmtPct(r.max_dd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>
      ))}
    </div>
  );
}
