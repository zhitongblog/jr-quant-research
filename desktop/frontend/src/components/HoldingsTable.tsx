import type { Holding } from "@/api";

export function HoldingsTable({
  holdings,
  onSelect,
}: {
  holdings: Holding[];
  onSelect?: (qlibSymbol: string) => void;
}) {
  if (!holdings.length) {
    return (
      <div className="text-xs text-muted italic px-2 py-3">暂无持仓</div>
    );
  }
  // Group by industry for readability
  const byInd = new Map<string, Holding[]>();
  for (const h of holdings) {
    const k = h.sw1_name || "未分类";
    byInd.set(k, [...(byInd.get(k) ?? []), h]);
  }
  const grouped = Array.from(byInd.entries()).sort((a, b) => b[1].length - a[1].length);

  return (
    <div className="text-xs space-y-3 max-h-[480px] overflow-auto">
      {grouped.map(([ind, items]) => (
        <div key={ind}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-muted text-[11px] tracking-wider uppercase">
              {ind}
            </span>
            <span className="text-[10px] text-muted">{items.length}</span>
          </div>
          <div className="grid grid-cols-1 gap-px bg-border/50 rounded-md overflow-hidden">
            {items.map((h) => (
              <button
                key={h.qlib_symbol}
                type="button"
                onClick={() => onSelect?.(h.qlib_symbol)}
                className="bg-panel-2 px-2 py-1.5 flex items-center justify-between text-left hover:bg-accent/10 transition"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-mono text-muted text-[11px] shrink-0">
                    {h.symbol}
                  </span>
                  <span className="truncate text-fg">{h.name || "—"}</span>
                </div>
                {onSelect && (
                  <span className="text-[10px] text-muted shrink-0">详情 →</span>
                )}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
