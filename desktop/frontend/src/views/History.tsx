import { useEffect, useState } from "react";
import { api, type Portfolio } from "@/api";
import { Card, CardBody, CardHeader, Pill } from "@/components/Card";
import { HoldingsTable } from "@/components/HoldingsTable";

export function HistoryView({
  refreshKey,
  onSelectSymbol,
}: {
  refreshKey: number;
  onSelectSymbol?: (s: string) => void;
}) {
  const [dates, setDates] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [data, setData] = useState<Portfolio | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    api
      .portfolioHistory()
      .then((r) => {
        setDates(r.dates);
        if (r.dates.length > 0) setSelected(r.dates[r.dates.length - 1]);
      })
      .catch((e) => setError(String(e)));
  }, [refreshKey]);

  useEffect(() => {
    if (!selected) return;
    setData(null);
    api
      .portfolioByDate(selected)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [selected]);

  if (error) return <div className="p-6 text-down text-sm">加载失败：{error}</div>;

  return (
    <div className="p-6 space-y-6 overflow-auto">
      <div className="flex items-baseline gap-3">
        <h1 className="text-2xl font-semibold text-fg">历史预测档案</h1>
        <Pill>{dates.length} 月</Pill>
      </div>

      <div className="flex flex-wrap gap-2">
        {dates.length === 0 ? (
          <span className="text-sm text-muted">尚无历史预测</span>
        ) : (
          dates.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setSelected(d)}
              className={`px-3 py-1.5 rounded-md text-xs font-mono border transition ${
                selected === d
                  ? "bg-accent/10 text-accent border-accent/40"
                  : "bg-panel border-border text-muted hover:text-fg hover:border-accent/30"
              }`}
            >
              {d}
            </button>
          ))
        )}
      </div>

      {selected && !data && (
        <div className="text-muted text-sm">加载 {selected}…</div>
      )}
      {data && (
        <div className="grid grid-cols-3 gap-4">
          <Card>
            <CardHeader title="Path A 当月持仓" right={<Pill>{data.path_a.holdings.length}</Pill>} />
            <CardBody><HoldingsTable holdings={data.path_a.holdings} onSelect={onSelectSymbol} /></CardBody>
          </Card>
          <Card>
            <CardHeader title="Path D 当月持仓" right={<Pill>{data.path_d.holdings.length}</Pill>} />
            <CardBody>
              <div className="mb-3 text-xs space-y-2">
                {data.path_d.llm_picks.map((p) => (
                  <div key={p.sw1_code} className="text-muted">
                    <span className="text-accent font-mono">{p.sw1_code}</span>{" "}
                    <span className="text-fg">{p.sw1_name}</span> — {p.rationale}
                  </div>
                ))}
              </div>
              <HoldingsTable holdings={data.path_d.holdings} onSelect={onSelectSymbol} />
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Ensemble" right={<Pill>{data.ensemble.holdings.length}</Pill>} />
            <CardBody><HoldingsTable holdings={data.ensemble.holdings} onSelect={onSelectSymbol} /></CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
