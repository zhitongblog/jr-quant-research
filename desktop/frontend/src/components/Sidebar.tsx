import type { ViewKey } from "@/App";
import { useProfile } from "@/profile";

const ITEMS: { key: ViewKey; label: string; subtitle: string; beginner: boolean }[] = [
  { key: "overview",   label: "本月推荐",   subtitle: "今天买什么",       beginner: true },
  { key: "my_trades",  label: "我的交易",   subtitle: "持仓 + 录入交易",  beginner: true },
  { key: "trades",     label: "操作单",     subtitle: "完整操作清单",     beginner: false },
  { key: "portfolio",  label: "持仓 + LLM", subtitle: "深入看推荐逻辑",   beginner: false },
  { key: "news",       label: "新闻面",     subtitle: "AI 上下文",        beginner: false },
  { key: "benchmark",  label: "vs 沪深300", subtitle: "跑得过 ETF 吗",    beginner: false },
  { key: "performance",label: "绩效追踪",   subtitle: "月度评估累积",     beginner: false },
  { key: "backtest",   label: "回测对比",   subtitle: "历史多策略",       beginner: false },
  { key: "history",    label: "历史预测",   subtitle: "按月浏览",         beginner: false },
  { key: "settings",   label: "设置",       subtitle: "本金 / 风险 / 模式", beginner: true },
];

export function Sidebar({
  current,
  onChange,
}: {
  current: ViewKey;
  onChange: (k: ViewKey) => void;
}) {
  const [profile, updateProfile] = useProfile();
  const isBeginner = profile.mode === "beginner";
  const visible = isBeginner ? ITEMS.filter((i) => i.beginner) : ITEMS;

  return (
    <aside className="w-56 border-r border-border bg-panel flex flex-col">
      <div className="px-4 py-4 border-b border-border">
        <div className="text-base font-semibold text-fg">jr 量化研究</div>
        <div className="text-xs text-muted mt-0.5">
          {isBeginner ? "新手模式 · 简化界面" : "专业模式 · 全部功能"}
        </div>
      </div>
      <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
        {visible.map((it) => (
          <button
            key={it.key}
            type="button"
            onClick={() => onChange(it.key)}
            className={`w-full text-left px-3 py-2 rounded-md transition-colors ${
              current === it.key
                ? "bg-accent/10 text-accent border border-accent/30"
                : "text-fg hover:bg-panel-2 border border-transparent"
            }`}
          >
            <div className="text-sm font-medium">{it.label}</div>
            <div className="text-xs text-muted mt-0.5">{it.subtitle}</div>
          </button>
        ))}
      </nav>
      <div className="p-3 border-t border-border">
        <button
          type="button"
          onClick={() => updateProfile({ mode: isBeginner ? "expert" : "beginner" })}
          className="w-full px-2 py-1.5 rounded text-xs bg-panel-2 hover:bg-panel-2/80 text-muted border border-border hover:text-fg"
        >
          切换到{isBeginner ? "专业" : "新手"}模式
        </button>
        <div className="text-[10px] text-muted mt-2 text-center">v0.1 · localhost:8765</div>
      </div>
    </aside>
  );
}
