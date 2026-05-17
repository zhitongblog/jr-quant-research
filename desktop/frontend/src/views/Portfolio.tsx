import { useEffect, useState } from "react";
import { api, type Portfolio } from "@/api";
import { Card, CardBody, CardHeader, Pill } from "@/components/Card";
import { HoldingsTable } from "@/components/HoldingsTable";

export function PortfolioView({
  refreshKey,
  onSelectSymbol,
}: {
  refreshKey: number;
  onSelectSymbol?: (s: string) => void;
}) {
  const [data, setData] = useState<Portfolio | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    setData(null);
    api
      .portfolioLatest()
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [refreshKey]);

  if (error) {
    return (
      <div className="p-6 text-down text-sm">
        加载失败：{error}
      </div>
    );
  }
  if (!data) {
    return <div className="p-6 text-muted text-sm">加载中…</div>;
  }

  return (
    <div className="p-6 space-y-6 overflow-auto">
      <div className="flex items-baseline gap-3">
        <h1 className="text-2xl font-semibold text-fg">最新持仓建议</h1>
        <Pill>{data.date}</Pill>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardHeader
            title="Path A · 行业-LGB"
            subtitle="50 持仓，industry feature + relative factor"
            right={<Pill tone="accent">{data.path_a.holdings.length}</Pill>}
          />
          <CardBody>
            <HoldingsTable holdings={data.path_a.holdings} onSelect={onSelectSymbol} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Path D · LLM 行业"
            subtitle="DeepSeek 行业宏观判断"
            right={<Pill tone="accent">{data.path_d.holdings.length}</Pill>}
          />
          <CardBody>
            <HoldingsTable holdings={data.path_d.holdings} onSelect={onSelectSymbol} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Ensemble"
            subtitle={`A∩D = ${data.ensemble.intersection_size}，其余由 A 补齐`}
            right={<Pill tone="accent">{data.ensemble.holdings.length}</Pill>}
          />
          <CardBody>
            <HoldingsTable holdings={data.ensemble.holdings} onSelect={onSelectSymbol} />
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="LLM 宏观判断" subtitle="DeepSeek-V4-Pro 当月分析" />
        <CardBody className="space-y-4">
          {data.path_d.llm_picks.map((p) => (
            <div key={p.sw1_code} className="border-l-2 border-accent/50 pl-3">
              <div className="flex items-center gap-2 mb-1">
                <Pill tone="accent">{p.sw1_code}</Pill>
                <span className="text-fg font-medium">{p.sw1_name}</span>
              </div>
              <div className="text-sm text-muted leading-relaxed">
                {p.rationale}
              </div>
            </div>
          ))}
          {data.path_d.llm_macro && (
            <div className="mt-2 pt-3 border-t border-border">
              <div className="text-xs text-muted mb-1">大盘判断</div>
              <div className="text-sm text-fg leading-relaxed">
                {data.path_d.llm_macro}
              </div>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
