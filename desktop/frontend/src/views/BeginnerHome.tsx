import { useEffect, useMemo, useState } from "react";
import { api, type Portfolio, type PriceLatestRow, type PositionsResponse, type TradeIn } from "@/api";
import { Card, CardBody, CardHeader, Pill } from "@/components/Card";
import {
  fmtMoney, useProfile, deriveHoldingCount, MIN_CAPITAL,
  RISK_PROFILE,
} from "@/profile";
import type { ViewKey } from "@/App";

const ROUND_LOT = 100;

interface Suggestion {
  qlib_symbol: string;
  symbol: string;
  name: string;
  sw1_name: string;
  close: number;
  buy_low: number;
  buy_high: number;
  shares: number;
  amount: number;
  llm_reason?: string;
}

export function BeginnerHome({
  refreshKey,
  onNavigate,
  onSelectSymbol,
}: {
  refreshKey: number;
  onNavigate: (v: ViewKey) => void;
  onSelectSymbol?: (s: string) => void;
}) {
  const [profile] = useProfile();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [prices, setPrices] = useState<Record<string, PriceLatestRow>>({});
  const [positions, setPositions] = useState<PositionsResponse | null>(null);
  const [quickBuy, setQuickBuy] = useState<Suggestion | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    api.portfolioLatest().then(setPortfolio).catch(() => setPortfolio(null));
    api.tradesPositions().then(setPositions).catch(() => setPositions(null));
  }, [refreshKey]);

  useEffect(() => {
    if (!portfolio) return;
    const syms = portfolio.ensemble.holdings.map((h) => h.qlib_symbol);
    if (!syms.length) return;
    api.pricesLatest(syms.slice(0, 50)).then((r) => {
      const map: Record<string, PriceLatestRow> = {};
      for (const row of r.rows) map[row.qlib_symbol] = row;
      setPrices(map);
    });
  }, [portfolio]);

  // Compute suggestions list (top-K of Ensemble, with prices and reasons)
  const suggestions = useMemo<Suggestion[]>(() => {
    if (!portfolio || !profile.capital) return [];
    const k = deriveHoldingCount(profile.capital, profile.cashReservePct);
    const invested = profile.capital * (1 - profile.cashReservePct);
    const per = invested / k;
    const bandPct = profile.buyBandPct;
    // LLM picks indexed by sw1_code → reason
    const reasonByInd = new Map<string, string>();
    for (const p of portfolio.path_d.llm_picks) {
      reasonByInd.set(p.sw1_code, p.rationale);
    }
    const out: Suggestion[] = [];
    for (const h of portfolio.ensemble.holdings.slice(0, k)) {
      const px = prices[h.qlib_symbol]?.close ?? null;
      if (!px) continue;
      const oneLot = px * ROUND_LOT;
      if (oneLot > per * 1.5) continue;
      const shares = Math.max(0, Math.floor(per / px / ROUND_LOT) * ROUND_LOT);
      if (shares === 0) continue;
      out.push({
        qlib_symbol: h.qlib_symbol,
        symbol: h.symbol,
        name: h.name,
        sw1_name: h.sw1_name,
        close: px,
        buy_low: px * (1 - bandPct),
        buy_high: px * (1 + bandPct),
        shares,
        amount: shares * px,
        llm_reason: reasonByInd.get(h.sw1_code),
      });
    }
    return out;
  }, [portfolio, prices, profile]);

  const totalCost = suggestions.reduce((acc, s) => acc + s.amount, 0);
  const risk = RISK_PROFILE[profile.riskTolerance];
  const setupOk = profile.capital >= MIN_CAPITAL && profile.acceptedRiskWarning;

  // -------- setup needed ----------
  if (profile.capital === 0 || !profile.acceptedRiskWarning) {
    return (
      <div className="p-6 max-w-2xl mx-auto space-y-6">
        <div className="text-center pt-4">
          <h1 className="text-3xl font-semibold text-fg">欢迎使用 jr 量化研究</h1>
          <p className="text-sm text-muted mt-2">先回答 2 个问题，再开始</p>
        </div>
        <Card className="border-accent/30">
          <CardBody className="space-y-4">
            <Step n={1} done={profile.capital > 0 && profile.capital >= MIN_CAPITAL}
              title="设置本金"
              desc={profile.capital >= MIN_CAPITAL
                ? `已设置 ${fmtMoney(profile.capital)}`
                : profile.capital > 0
                  ? `当前 ${fmtMoney(profile.capital)} (建议 ≥¥10000)`
                  : "你愿意拿多少钱来跟这套系统？建议 ≥¥10000"} />
            <Step n={2} done={profile.acceptedRiskWarning}
              title="接受风险声明"
              desc={profile.acceptedRiskWarning ? "已接受" : "理解这是研究工具不是保证赚钱"} />
            <button type="button" onClick={() => onNavigate("settings")}
              className="w-full px-4 py-2.5 rounded-md bg-accent/15 hover:bg-accent/25 text-accent border border-accent/40 text-sm font-medium">
              去设置页填这两项 →
            </button>
          </CardBody>
        </Card>
      </div>
    );
  }

  // -------- main beginner view ----------
  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6 overflow-auto">
      {/* Greeting */}
      <div>
        <h1 className="text-3xl font-semibold text-fg">本月推荐</h1>
        <div className="text-sm text-muted mt-1">
          {portfolio
            ? `模型最近更新于 ${portfolio.date}`
            : "模型尚未运行——点右上角「立即跑月度更新」"}
        </div>
      </div>

      {/* Macro view from LLM */}
      {portfolio?.path_d.llm_macro && (
        <Card className="border-accent/30 bg-accent/5">
          <CardBody>
            <div className="flex items-start gap-3">
              <div className="text-2xl mt-0.5">💡</div>
              <div>
                <div className="text-xs text-accent font-medium mb-1">AI 对当前市场的判断</div>
                <div className="text-sm text-fg leading-relaxed">{portfolio.path_d.llm_macro}</div>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Industry picks recap */}
      {portfolio && portfolio.path_d.llm_picks.length > 0 && (
        <Card>
          <CardHeader title="AI 看好的 3 个行业（不是推荐的 3 只股票！）"
            subtitle="LLM 每月固定挑 3 个有潜力的行业方向；下面的具体股票数会按你的本金动态变。" />
          <CardBody>
            <div className="grid grid-cols-3 gap-3">
              {portfolio.path_d.llm_picks.map((p) => (
                <div key={p.sw1_code} className="bg-panel-2 rounded-md p-3 border border-border">
                  <div className="text-base font-medium text-accent">{p.sw1_name}</div>
                  <div className="text-xs text-muted leading-relaxed mt-2">{p.rationale}</div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Suggestion cards */}
      <div>
        <div className="flex items-baseline gap-3 mb-3">
          <h2 className="text-xl font-semibold text-fg">具体买什么</h2>
          <Pill>{suggestions.length} 只</Pill>
          <span className="text-sm text-muted">合计约 {fmtMoney(totalCost)}</span>
        </div>
        <div className="mb-3 text-xs text-muted leading-relaxed bg-panel-2 border border-border/50 rounded-md px-3 py-2">
          数量怎么算的：本金 <span className="font-mono text-fg">{fmtMoney(profile.capital)}</span> × 投入比例{" "}
          <span className="font-mono text-fg">{((1 - profile.cashReservePct) * 100).toFixed(0)}%</span>{" "}
          ÷ 每只 ¥2000（A 股一手 100 股 × 中位数股价）
          {" = "}
          <span className="font-mono text-accent">
            目标 {deriveHoldingCount(profile.capital, profile.cashReservePct)} 只
          </span>
          {suggestions.length < deriveHoldingCount(profile.capital, profile.cashReservePct) && (
            <>
              ，实际 <span className="font-mono text-accent">{suggestions.length}</span> 只——
              其余因为一手价格过高被自动跳过（如茅台一手 ¥15 万）
            </>
          )}
          。本金越大 → 持仓越分散；调整持仓数请去 <button type="button" onClick={() => onNavigate("settings")} className="text-accent underline">设置</button>。
        </div>

        {suggestions.length === 0 ? (
          <Card>
            <CardBody>
              <div className="text-sm text-muted leading-relaxed">
                没有可买的票。可能原因：(1) 本金过低买不起一手；(2) 模型还没运行——
                点右上角"立即跑月度更新"。
              </div>
            </CardBody>
          </Card>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {suggestions.map((s) => (
              <SuggestionCard
                key={s.qlib_symbol}
                s={s}
                onDetail={() => onSelectSymbol?.(s.qlib_symbol)}
                onBought={() => setQuickBuy(s)}
              />
            ))}
          </div>
        )}
      </div>

      {/* My positions summary */}
      {positions && positions.positions.length > 0 && (
        <Card>
          <CardHeader
            title="你目前持仓"
            subtitle={`${positions.summary.n_positions} 只 · 总市值 ${fmtMoney(positions.summary.total_market_value)}`}
            right={
              <span className={`text-sm font-mono ${
                positions.summary.total_pnl >= 0 ? "text-up" : "text-down"
              }`}>
                浮盈 {positions.summary.total_pnl >= 0 ? "+" : ""}
                {fmtMoney(positions.summary.total_pnl)}
              </span>
            }
          />
          <CardBody>
            <button type="button" onClick={() => onNavigate("my_trades")}
              className="text-sm text-accent hover:underline">
              查看完整持仓 + 交易记录 →
            </button>
          </CardBody>
        </Card>
      )}

      {/* Bottom: switch to expert */}
      <Card className="border-muted/30">
        <CardBody>
          <div className="flex items-center justify-between text-sm">
            <div>
              <div className="text-fg font-medium">想看更多？</div>
              <div className="text-xs text-muted mt-1">
                K 线分析、回测对比、行业轮动、新闻面、绩效追踪等进阶功能在专业模式
              </div>
            </div>
            <button type="button" onClick={() => onNavigate("settings")}
              className="px-3 py-1.5 rounded-md bg-panel-2 hover:bg-panel-2/80 text-fg border border-border text-sm">
              切换到专业模式
            </button>
          </div>
        </CardBody>
      </Card>

      {/* Disclosure */}
      <div className="text-xs text-muted text-center pt-2">
        ⚠️ 本系统不构成投资建议。{risk.label}模式下最坏可能亏损 {(risk.expectedMaxDD * 100).toFixed(0)}%。
        实盘前请先用模拟账号跟 1-2 个月。
      </div>

      {/* Quick-buy modal */}
      {quickBuy && (
        <QuickBuyModal
          suggestion={quickBuy}
          onClose={() => setQuickBuy(null)}
          onSaved={() => {
            setQuickBuy(null);
            setToast("✓ 已记录到「我的交易」");
            setTimeout(() => setToast(null), 2500);
            api.tradesPositions().then(setPositions).catch(() => {});
          }}
        />
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 bg-up/20 border border-up/40 text-up px-4 py-2 rounded-md text-sm shadow-lg">
          {toast}
        </div>
      )}

      {!setupOk && (
        <div className="text-xs text-down text-center">需要先在设置页完成本金 + 风险声明</div>
      )}
    </div>
  );
}

// -------------------------- Suggestion Card --------------------------

function SuggestionCard({ s, onDetail, onBought }: {
  s: Suggestion;
  onDetail: () => void;
  onBought: () => void;
}) {
  const copy = async () => {
    const txt = `${s.symbol} ${s.name} · 买入区间 ¥${s.buy_low.toFixed(2)} ~ ¥${s.buy_high.toFixed(2)} · ${s.shares} 股 · 约 ${fmtMoney(s.amount)}`;
    try {
      await navigator.clipboard.writeText(txt);
      alert("已复制到剪贴板");
    } catch {
      window.prompt("手动复制：", txt);
    }
  };
  return (
    <div className="bg-panel border border-border rounded-lg p-4 flex flex-col gap-3 hover:border-accent/40 transition">
      <div>
        <div className="flex items-baseline justify-between">
          <div>
            <span className="text-base font-semibold text-fg">{s.name}</span>
            <span className="ml-2 text-xs font-mono text-muted">{s.symbol}</span>
          </div>
          <Pill>{s.sw1_name}</Pill>
        </div>
        <div className="text-2xl font-mono text-accent mt-1">¥{s.close.toFixed(2)}</div>
      </div>

      <div className="bg-panel-2 rounded p-2.5 text-sm">
        <div className="text-xs text-muted mb-1">建议买入价</div>
        <div className="font-mono">
          <span className="text-up">¥{s.buy_low.toFixed(2)}</span>
          <span className="text-muted"> ~ </span>
          <span className="text-down">¥{s.buy_high.toFixed(2)}</span>
        </div>
        <div className="text-[11px] text-muted mt-1">
          高于上限 → 当天别追。低于下限 → 可能基本面有变，谨慎接刀。
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-border pt-2">
        <div className="text-sm">
          买 <span className="font-mono text-accent">{s.shares}</span> 股
          <span className="text-muted"> ({s.shares / 100} 手)</span>
        </div>
        <div className="text-sm font-mono">{fmtMoney(s.amount)}</div>
      </div>

      {s.llm_reason && (
        <div className="text-xs text-muted leading-relaxed border-l-2 border-accent/40 pl-2">
          {s.llm_reason}
        </div>
      )}

      <div className="flex gap-1.5 pt-1">
        <button type="button" onClick={copy}
          className="flex-1 px-2 py-1.5 rounded text-xs bg-panel-2 hover:bg-panel-2/70 border border-border text-fg">
          📋 复制
        </button>
        <button type="button" onClick={onDetail}
          className="flex-1 px-2 py-1.5 rounded text-xs bg-panel-2 hover:bg-panel-2/70 border border-border text-fg">
          📊 K 线
        </button>
        <button type="button" onClick={onBought}
          className="flex-1 px-2 py-1.5 rounded text-xs bg-up/15 hover:bg-up/25 border border-up/40 text-up font-medium">
          ✓ 我买了
        </button>
      </div>
    </div>
  );
}

// -------------------------- Quick-buy Modal --------------------------

function QuickBuyModal({ suggestion, onClose, onSaved }: {
  suggestion: Suggestion;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [shares, setShares] = useState(String(suggestion.shares));
  const [price, setPrice] = useState(suggestion.close.toFixed(2));
  const [fee, setFee] = useState("0");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    const sh = parseInt(shares); const px = parseFloat(price); const fe = parseFloat(fee) || 0;
    if (!Number.isFinite(sh) || sh <= 0) { alert("股数无效"); return; }
    if (!Number.isFinite(px) || px <= 0) { alert("价格无效"); return; }
    setSaving(true);
    try {
      const t: TradeIn = {
        trade_date: date, qlib_symbol: suggestion.qlib_symbol, side: "buy",
        shares: sh, price: px, fee: fe, note: "通过推荐卡片快速录入",
      };
      await api.tradesAdd(t);
      onSaved();
    } catch (e) {
      alert(`保存失败: ${e}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}>
      <div className="bg-bg border border-border rounded-lg p-6 w-full max-w-md shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-baseline justify-between mb-4">
          <div>
            <div className="text-base font-semibold text-fg">{suggestion.name}</div>
            <div className="text-xs text-muted font-mono">{suggestion.symbol}</div>
          </div>
          <button type="button" onClick={onClose}
            className="text-muted hover:text-fg text-xl">×</button>
        </div>

        <div className="space-y-3 text-sm">
          <Field label="日期">
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
              className="w-full px-2 py-1.5 bg-panel-2 border border-border rounded text-sm" />
          </Field>
          <div className="grid grid-cols-3 gap-2">
            <Field label="股数">
              <input type="number" step={100} min={100} value={shares}
                onChange={(e) => setShares(e.target.value)}
                className="w-full px-2 py-1.5 bg-panel-2 border border-border rounded text-sm font-mono" />
            </Field>
            <Field label="成交价">
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
          <div className="text-xs text-muted">
            金额 ≈ {fmtMoney(parseInt(shares || "0") * parseFloat(price || "0"))}
          </div>
        </div>

        <div className="flex gap-2 mt-5">
          <button type="button" onClick={onClose}
            className="flex-1 px-4 py-2 rounded bg-panel-2 hover:bg-panel-2/70 border border-border text-sm">
            取消
          </button>
          <button type="button" onClick={save} disabled={saving}
            className="flex-1 px-4 py-2 rounded bg-up/15 hover:bg-up/25 text-up border border-up/40 text-sm font-medium disabled:opacity-40">
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="text-[11px] text-muted mb-1">{label}</div>
      {children}
    </label>
  );
}

function Step({ n, title, desc, done }: { n: number; title: string; desc: string; done: boolean }) {
  return (
    <div className="flex items-start gap-3">
      <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
        done ? "bg-up/20 text-up border border-up/40" : "bg-panel-2 text-muted border border-border"
      }`}>
        {done ? "✓" : n}
      </div>
      <div className="flex-1">
        <div className={`text-sm font-medium ${done ? "text-fg" : "text-muted"}`}>{title}</div>
        <div className="text-xs text-muted mt-0.5">{desc}</div>
      </div>
    </div>
  );
}
