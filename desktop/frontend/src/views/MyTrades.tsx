import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Trade, type PositionsResponse, type StockSearchRow, type ImportPreview } from "@/api";
import { Card, CardBody, CardHeader, Pill } from "@/components/Card";
import { fmtMoney } from "@/profile";

export function MyTradesView({
  refreshKey,
  onSelectSymbol,
}: {
  refreshKey: number;
  onSelectSymbol?: (s: string) => void;
}) {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [positions, setPositions] = useState<PositionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [internalRefresh, setInternalRefresh] = useState(0);

  useEffect(() => {
    setError(null);
    api.tradesList().then((r) => setTrades(r.rows)).catch((e) => setError(String(e)));
    api.tradesPositions().then(setPositions).catch((e) => setError(String(e)));
  }, [refreshKey, internalRefresh]);

  const reload = () => setInternalRefresh((x) => x + 1);

  return (
    <div className="p-6 space-y-6 overflow-auto">
      <div className="flex items-baseline gap-3">
        <h1 className="text-2xl font-semibold text-fg">我的交易</h1>
        <Pill>{trades.length} 笔</Pill>
        {positions && (
          <Pill tone={positions.summary.total_pnl >= 0 ? "up" : "down"}>
            总盈亏 {positions.summary.total_pnl >= 0 ? "+" : ""}{fmtMoney(positions.summary.total_pnl)}
          </Pill>
        )}
      </div>

      {error && <div className="text-down text-sm">{error}</div>}

      <PositionsCard positions={positions} onSelectSymbol={onSelectSymbol} />

      <div className="grid grid-cols-2 gap-4">
        <ManualEntryCard onSaved={reload} />
        <CsvImportCard onCommitted={reload} />
      </div>

      <TradeLogCard trades={trades} onDeleted={reload} onSelectSymbol={onSelectSymbol} />
    </div>
  );
}

// -------------------------- Positions --------------------------

function PositionsCard({ positions, onSelectSymbol }: {
  positions: PositionsResponse | null;
  onSelectSymbol?: (s: string) => void;
}) {
  if (!positions || positions.positions.length === 0) {
    return (
      <Card>
        <CardHeader title="我的当前持仓" subtitle="录入买入交易后会自动计算" />
        <CardBody>
          <div className="text-sm text-muted">尚无持仓。先在下面录入或导入交易。</div>
        </CardBody>
      </Card>
    );
  }
  const s = positions.summary;
  return (
    <Card>
      <CardHeader
        title="我的当前持仓"
        subtitle={`${s.n_positions} 只 · 总市值 ${fmtMoney(s.total_market_value)} · 成本 ${fmtMoney(s.total_cost_basis)}`}
        right={
          <div className="flex gap-3 text-xs">
            <span>浮盈 <span className={s.unrealized_pnl >= 0 ? "text-up" : "text-down"}>
              {s.unrealized_pnl >= 0 ? "+" : ""}{fmtMoney(s.unrealized_pnl)}
            </span></span>
            <span>已实现 <span className={s.realized_pnl >= 0 ? "text-up" : "text-down"}>
              {s.realized_pnl >= 0 ? "+" : ""}{fmtMoney(s.realized_pnl)}
            </span></span>
            <span>合计 <span className={`font-medium ${s.total_pnl >= 0 ? "text-up" : "text-down"}`}>
              {s.total_pnl >= 0 ? "+" : ""}{fmtMoney(s.total_pnl)}
              {s.pnl_pct != null && (
                <span className="ml-1">({s.pnl_pct >= 0 ? "+" : ""}{(s.pnl_pct * 100).toFixed(2)}%)</span>
              )}
            </span></span>
          </div>
        }
      />
      <CardBody>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-muted text-xs border-b border-border">
              <th className="text-left py-2 font-normal">代码/名称</th>
              <th className="text-left py-2 font-normal">行业</th>
              <th className="text-right py-2 font-normal">持仓</th>
              <th className="text-right py-2 font-normal">成本/现价</th>
              <th className="text-right py-2 font-normal">市值</th>
              <th className="text-right py-2 font-normal">浮盈</th>
            </tr>
          </thead>
          <tbody>
            {positions.positions.map((p) => (
              <tr key={p.qlib_symbol}
                onClick={() => onSelectSymbol?.(p.qlib_symbol)}
                className="border-b border-border/30 cursor-pointer hover:bg-panel-2/40">
                <td className="py-2">
                  <div className="font-mono text-xs text-muted">{p.symbol}</div>
                  <div className="text-fg">{p.name}</div>
                </td>
                <td className="py-2 text-muted text-xs">{p.sw1_name}</td>
                <td className="py-2 text-right font-mono">{p.shares}</td>
                <td className="py-2 text-right font-mono text-xs">
                  <div className="text-muted">¥{p.avg_cost.toFixed(2)}</div>
                  <div>¥{p.current_price?.toFixed(2) ?? "—"}</div>
                </td>
                <td className="py-2 text-right font-mono">
                  {p.market_value != null ? fmtMoney(p.market_value) : "—"}
                </td>
                <td className={`py-2 text-right font-mono ${
                  p.unrealized_pnl == null ? "" : p.unrealized_pnl >= 0 ? "text-up" : "text-down"
                }`}>
                  {p.unrealized_pnl == null ? "—"
                    : `${p.unrealized_pnl >= 0 ? "+" : ""}${fmtMoney(p.unrealized_pnl)}`}
                  {p.pnl_pct != null && (
                    <div className="text-[10px] text-muted">
                      {p.pnl_pct >= 0 ? "+" : ""}{(p.pnl_pct * 100).toFixed(2)}%
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}

// -------------------------- Manual Entry --------------------------

function ManualEntryCard({ onSaved }: { onSaved: () => void }) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<StockSearchRow | null>(null);
  const [matches, setMatches] = useState<StockSearchRow[]>([]);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [shares, setShares] = useState<string>("100");
  const [price, setPrice] = useState<string>("");
  const [fee, setFee] = useState<string>("0");
  const [note, setNote] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const searchTimeout = useRef<number | null>(null);

  useEffect(() => {
    if (searchTimeout.current) clearTimeout(searchTimeout.current);
    if (!query.trim() || picked) return;
    searchTimeout.current = window.setTimeout(() => {
      api.stocksSearch(query).then((r) => setMatches(r.rows)).catch(() => setMatches([]));
    }, 200);
  }, [query, picked]);

  const submit = async () => {
    if (!picked) { setMsg({ kind: "err", text: "请选择股票" }); return; }
    const sh = parseInt(shares); const px = parseFloat(price); const fe = parseFloat(fee) || 0;
    if (!Number.isFinite(sh) || sh <= 0) { setMsg({ kind: "err", text: "股数无效" }); return; }
    if (!Number.isFinite(px) || px <= 0) { setMsg({ kind: "err", text: "价格无效" }); return; }
    setBusy(true); setMsg(null);
    try {
      await api.tradesAdd({
        trade_date: date, qlib_symbol: picked.qlib_symbol, side,
        shares: sh, price: px, fee: fe, note,
      });
      setMsg({ kind: "ok", text: "已添加" });
      setPicked(null); setQuery(""); setShares("100"); setPrice(""); setFee("0"); setNote("");
      onSaved();
    } catch (e) {
      setMsg({ kind: "err", text: String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader title="手动录入" subtitle="一笔成交一行" />
      <CardBody className="space-y-3">
        <div className="grid grid-cols-2 gap-2 text-xs">
          <Field label="日期">
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
              className="w-full px-2 py-1.5 bg-panel-2 border border-border rounded text-sm" />
          </Field>
          <Field label="买卖">
            <div className="flex gap-1">
              {(["buy", "sell"] as const).map((s) => (
                <button key={s} type="button" onClick={() => setSide(s)}
                  className={`flex-1 px-2 py-1.5 rounded text-sm border ${
                    side === s
                      ? s === "buy" ? "bg-up/15 text-up border-up/40" : "bg-down/15 text-down border-down/40"
                      : "bg-panel-2 text-muted border-border"
                  }`}
                >{s === "buy" ? "买入" : "卖出"}</button>
              ))}
            </div>
          </Field>
        </div>

        <Field label="股票（代码或名称）">
          <div className="relative">
            <input
              type="text"
              value={picked ? `${picked.symbol} ${picked.name}` : query}
              onChange={(e) => { setPicked(null); setQuery(e.target.value); }}
              placeholder="例如 600000 或 浦发"
              className="w-full px-2 py-1.5 bg-panel-2 border border-border rounded text-sm"
            />
            {!picked && matches.length > 0 && query.trim() && (
              <div className="absolute z-10 mt-1 w-full max-h-48 overflow-y-auto bg-panel border border-border rounded-md shadow-lg">
                {matches.map((m) => (
                  <button key={m.qlib_symbol} type="button"
                    onClick={() => { setPicked(m); setMatches([]); }}
                    className="w-full text-left px-2 py-1.5 hover:bg-panel-2 text-xs border-b border-border/30 last:border-b-0">
                    <span className="font-mono text-muted">{m.symbol}</span>{" "}
                    <span className="text-fg">{m.name}</span>{" "}
                    <span className="text-[10px] text-muted">{m.sw1_name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </Field>

        <div className="grid grid-cols-3 gap-2">
          <Field label="股数（一手=100）">
            <input type="number" min={100} step={100} value={shares}
              onChange={(e) => setShares(e.target.value)}
              className="w-full px-2 py-1.5 bg-panel-2 border border-border rounded text-sm font-mono" />
          </Field>
          <Field label="成交价 ¥">
            <input type="number" step="0.01" value={price}
              onChange={(e) => setPrice(e.target.value)}
              className="w-full px-2 py-1.5 bg-panel-2 border border-border rounded text-sm font-mono" />
          </Field>
          <Field label="手续费">
            <input type="number" step="0.01" value={fee}
              onChange={(e) => setFee(e.target.value)}
              className="w-full px-2 py-1.5 bg-panel-2 border border-border rounded text-sm font-mono" />
          </Field>
        </div>

        <Field label="备注（可选）">
          <input type="text" value={note} onChange={(e) => setNote(e.target.value)}
            placeholder="例如：跟 Ensemble 月度推荐"
            className="w-full px-2 py-1.5 bg-panel-2 border border-border rounded text-sm" />
        </Field>

        <div className="flex items-center justify-between pt-2">
          <span className="text-xs text-muted">
            {picked && shares && price
              ? `≈ ${fmtMoney(parseInt(shares) * parseFloat(price))}`
              : ""}
          </span>
          <button type="button" onClick={submit} disabled={busy}
            className="px-4 py-1.5 rounded-md bg-accent/15 hover:bg-accent/25 text-accent border border-accent/40 text-sm disabled:opacity-40">
            {busy ? "保存中..." : "保存"}
          </button>
        </div>
        {msg && (
          <div className={`text-xs ${msg.kind === "ok" ? "text-up" : "text-down"}`}>
            {msg.text}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

// -------------------------- CSV Import --------------------------

function CsvImportCard({ onCommitted }: { onCommitted: () => void }) {
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const onFile = async (file: File | null) => {
    setSelectedFile(file);
    setPreview(null);
    setError(null);
    if (!file) return;
    setBusy(true);
    try {
      const r = await api.tradesImport(file, false);
      setPreview(r);
      if (!r.ok && r.error) setError(r.error);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const commit = async () => {
    if (!selectedFile) return;
    setBusy(true); setError(null);
    try {
      const r = await api.tradesImport(selectedFile, true);
      setPreview(r);
      if (r.committed) {
        onCommitted();
        if (fileRef.current) fileRef.current.value = "";
        setSelectedFile(null);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader title="导入券商 CSV"
        subtitle="支持东方财富 / 华泰 / 国信 / 同花顺等导出格式 (UTF-8 / GBK 自动识别)" />
      <CardBody className="space-y-3">
        <div>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.txt"
            onChange={(e) => onFile(e.target.files?.[0] ?? null)}
            className="w-full text-xs file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-accent/15 file:text-accent hover:file:bg-accent/25 cursor-pointer"
          />
        </div>

        {busy && <div className="text-xs text-muted">解析中…</div>}
        {error && <div className="text-xs text-down break-all">{error}</div>}

        {preview && (
          <div className="space-y-2 text-xs">
            <div className="flex items-center gap-3">
              <Pill tone={preview.ok ? "up" : "down"}>
                {preview.ok ? `识别 ${preview.n_parsed ?? 0} 条` : "识别失败"}
              </Pill>
              {preview.encoding && <span className="text-muted">编码 {preview.encoding}</span>}
              {(preview.n_errors ?? 0) > 0 && (
                <span className="text-down">⚠️ {preview.n_errors} 条解析失败</span>
              )}
            </div>
            {preview.column_mapping && (
              <details className="text-muted">
                <summary className="cursor-pointer">字段映射</summary>
                <pre className="bg-panel-2 p-2 rounded mt-1 text-[10px] overflow-x-auto">
                  {JSON.stringify(preview.column_mapping, null, 2)}
                </pre>
              </details>
            )}
            {preview.preview && preview.preview.length > 0 && (
              <div className="max-h-48 overflow-y-auto bg-panel-2 rounded">
                <table className="w-full text-[11px]">
                  <thead className="text-muted">
                    <tr className="border-b border-border">
                      <th className="text-left p-1">日期</th>
                      <th className="text-left p-1">代码</th>
                      <th className="text-left p-1">买卖</th>
                      <th className="text-right p-1">股数</th>
                      <th className="text-right p-1">价格</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.preview.slice(0, 20).map((t) => (
                      <tr key={t.id}>
                        <td className="p-1 font-mono">{t.trade_date}</td>
                        <td className="p-1">{t.symbol} {t.name}</td>
                        <td className={`p-1 ${t.side === "buy" ? "text-up" : "text-down"}`}>
                          {t.side === "buy" ? "买" : "卖"}
                        </td>
                        <td className="p-1 text-right font-mono">{t.shares}</td>
                        <td className="p-1 text-right font-mono">¥{t.price.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {(preview.preview.length > 20) && (
                  <div className="text-center text-muted text-[10px] py-1">
                    +{preview.preview.length - 20} 条未展示
                  </div>
                )}
              </div>
            )}
            {preview.ok && (preview.n_parsed ?? 0) > 0 && !preview.committed && (
              <div className="flex justify-end pt-1">
                <button type="button" onClick={commit} disabled={busy}
                  className="px-3 py-1.5 rounded-md bg-up/15 hover:bg-up/25 text-up border border-up/40 text-xs">
                  确认导入 {preview.n_parsed} 条
                </button>
              </div>
            )}
            {preview.committed && (
              <div className="text-up text-xs">✓ 已导入</div>
            )}
          </div>
        )}

        {!preview && !busy && (
          <div className="text-[11px] text-muted leading-relaxed">
            从券商客户端导出"历史成交"CSV 文件，拖拽或选择上传。
            系统会先预览解析结果，确认无误后再点"确认导入"。
          </div>
        )}
      </CardBody>
    </Card>
  );
}

// -------------------------- Trade Log Table --------------------------

function TradeLogCard({ trades, onDeleted, onSelectSymbol }: {
  trades: Trade[];
  onDeleted: () => void;
  onSelectSymbol?: (s: string) => void;
}) {
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState<Trade | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    if (!filter) return trades;
    const f = filter.toLowerCase();
    return trades.filter((t) =>
      t.symbol.includes(f) || t.name.toLowerCase().includes(f) || t.sw1_name.includes(filter)
    );
  }, [trades, filter]);

  const toggleSel = (id: string) => {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    setSelected(new Set(filtered.map((t) => t.id)));
  };
  const clearSel = () => setSelected(new Set());

  const del = async (id: string) => {
    if (!window.confirm("确定删除这一笔？")) return;
    try {
      await api.tradesDelete(id);
      setSelected((s) => { const n = new Set(s); n.delete(id); return n; });
      onDeleted();
    } catch (e) {
      alert(String(e));
    }
  };

  const delMany = async () => {
    if (selected.size === 0) return;
    if (!window.confirm(`确定删除选中的 ${selected.size} 笔？`)) return;
    try {
      for (const id of selected) {
        await api.tradesDelete(id);
      }
      setSelected(new Set());
      onDeleted();
    } catch (e) {
      alert(String(e));
    }
  };

  return (
    <Card>
      <CardHeader
        title="交易流水"
        subtitle={`${trades.length} 笔历史交易（按日期倒序，点 ✏️ 编辑、🗑️ 删除）`}
        right={
          <div className="flex items-center gap-2">
            {selected.size > 0 && (
              <button type="button" onClick={delMany}
                className="px-2 py-1 rounded bg-down/15 hover:bg-down/25 text-down border border-down/40 text-xs">
                批量删除 ({selected.size})
              </button>
            )}
            <input type="text" value={filter} onChange={(e) => setFilter(e.target.value)}
              placeholder="筛选 代码/名称/行业"
              className="px-2 py-1 bg-panel-2 border border-border rounded text-xs w-40" />
          </div>
        }
      />
      <CardBody>
        {trades.length === 0 ? (
          <div className="text-sm text-muted">尚无交易记录。在上方"手动录入"或"导入 CSV"添加。</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted text-xs border-b border-border">
                <th className="text-left py-2 font-normal w-8">
                  <input type="checkbox"
                    checked={selected.size > 0 && selected.size === filtered.length}
                    onChange={(e) => e.target.checked ? selectAll() : clearSel()}
                    className="accent-accent" />
                </th>
                <th className="text-left py-2 font-normal">日期</th>
                <th className="text-left py-2 font-normal">代码/名称</th>
                <th className="text-left py-2 font-normal">行业</th>
                <th className="text-right py-2 font-normal">方向</th>
                <th className="text-right py-2 font-normal">股数</th>
                <th className="text-right py-2 font-normal">价格</th>
                <th className="text-right py-2 font-normal">金额</th>
                <th className="text-right py-2 font-normal w-32">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => (
                editing?.id === t.id ? (
                  <EditRowInline key={t.id} trade={t}
                    onCancel={() => setEditing(null)}
                    onSaved={() => { setEditing(null); onDeleted(); }} />
                ) : (
                  <tr key={t.id} className="border-b border-border/30 hover:bg-panel-2/40">
                    <td className="py-2">
                      <input type="checkbox"
                        checked={selected.has(t.id)}
                        onChange={() => toggleSel(t.id)}
                        className="accent-accent" />
                    </td>
                    <td className="py-2 font-mono text-xs">{t.trade_date}</td>
                    <td className="py-2 cursor-pointer" onClick={() => onSelectSymbol?.(t.qlib_symbol)}>
                      <span className="font-mono text-xs text-muted">{t.symbol}</span>{" "}
                      <span className="text-fg">{t.name}</span>
                    </td>
                    <td className="py-2 text-muted text-xs">{t.sw1_name}</td>
                    <td className={`py-2 text-right text-xs font-medium ${
                      t.side === "buy" ? "text-up" : "text-down"
                    }`}>{t.side === "buy" ? "买入" : "卖出"}</td>
                    <td className="py-2 text-right font-mono">{t.shares}</td>
                    <td className="py-2 text-right font-mono">¥{t.price.toFixed(2)}</td>
                    <td className="py-2 text-right font-mono">{fmtMoney(t.amount)}</td>
                    <td className="py-2 text-right">
                      <button type="button" onClick={() => setEditing(t)}
                        className="px-2 py-0.5 rounded text-[11px] text-accent bg-accent/10 hover:bg-accent/20 border border-accent/30 mr-1">
                        ✏️ 编辑
                      </button>
                      <button type="button" onClick={() => del(t.id)}
                        className="px-2 py-0.5 rounded text-[11px] text-down bg-down/10 hover:bg-down/20 border border-down/30">
                        🗑️ 删除
                      </button>
                    </td>
                  </tr>
                )
              ))}
            </tbody>
          </table>
        )}
      </CardBody>
    </Card>
  );
}

function EditRowInline({ trade, onCancel, onSaved }: {
  trade: Trade;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [date, setDate] = useState(trade.trade_date);
  const [side, setSide] = useState<"buy" | "sell">(trade.side);
  const [shares, setShares] = useState(String(trade.shares));
  const [price, setPrice] = useState(String(trade.price));
  const [fee, setFee] = useState(String(trade.fee));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const save = async () => {
    setErr(null);
    const sh = parseInt(shares); const px = parseFloat(price); const fe = parseFloat(fee) || 0;
    if (!Number.isFinite(sh) || sh <= 0) { setErr("股数无效"); return; }
    if (!Number.isFinite(px) || px <= 0) { setErr("价格无效"); return; }
    setBusy(true);
    try {
      await api.tradesUpdate(trade.id, {
        trade_date: date, qlib_symbol: trade.qlib_symbol, side,
        shares: sh, price: px, fee: fe, note: trade.note,
      });
      onSaved();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <tr className="bg-accent/5 border-b border-accent/20">
      <td></td>
      <td className="py-2">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
          className="w-full px-1 py-0.5 bg-panel-2 border border-border rounded text-xs font-mono" />
      </td>
      <td className="py-2">
        <span className="font-mono text-xs text-muted">{trade.symbol}</span>{" "}
        <span className="text-fg">{trade.name}</span>
        <span className="text-[10px] text-muted ml-2">代码不可改</span>
      </td>
      <td className="py-2 text-muted text-xs">{trade.sw1_name}</td>
      <td className="py-2 text-right">
        <div className="flex gap-1 justify-end">
          {(["buy", "sell"] as const).map((s) => (
            <button key={s} type="button" onClick={() => setSide(s)}
              className={`px-1.5 py-0.5 rounded text-[11px] border ${
                side === s
                  ? s === "buy" ? "bg-up/15 text-up border-up/40" : "bg-down/15 text-down border-down/40"
                  : "bg-panel-2 text-muted border-border"
              }`}
            >{s === "buy" ? "买" : "卖"}</button>
          ))}
        </div>
      </td>
      <td className="py-2 text-right">
        <input type="number" min={100} step={100} value={shares}
          onChange={(e) => setShares(e.target.value)}
          className="w-20 px-1 py-0.5 bg-panel-2 border border-border rounded text-xs font-mono text-right" />
      </td>
      <td className="py-2 text-right">
        <input type="number" step="0.01" value={price}
          onChange={(e) => setPrice(e.target.value)}
          className="w-20 px-1 py-0.5 bg-panel-2 border border-border rounded text-xs font-mono text-right" />
      </td>
      <td className="py-2 text-right">
        <input type="number" step="0.01" value={fee}
          onChange={(e) => setFee(e.target.value)}
          placeholder="手续费"
          className="w-16 px-1 py-0.5 bg-panel-2 border border-border rounded text-xs font-mono text-right" />
      </td>
      <td className="py-2 text-right">
        <button type="button" onClick={save} disabled={busy}
          className="px-2 py-0.5 rounded text-[11px] text-up bg-up/15 border border-up/40 mr-1 disabled:opacity-40">
          {busy ? "..." : "保存"}
        </button>
        <button type="button" onClick={onCancel}
          className="px-2 py-0.5 rounded text-[11px] text-muted bg-panel-2 border border-border">
          取消
        </button>
        {err && <div className="text-[10px] text-down mt-1">{err}</div>}
      </td>
    </tr>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[11px] text-muted block mb-1">{label}</span>
      {children}
    </label>
  );
}
