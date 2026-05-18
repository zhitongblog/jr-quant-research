// User profile stored in localStorage. Drives the position sizer + warnings.

import { useEffect, useState } from "react";

export type Risk = "low" | "medium" | "high";

export type Mode = "beginner" | "expert";
export type Theme = "notion" | "trading";

export interface Profile {
  capital: number;             // total available capital (元)
  riskTolerance: Risk;         // affects max DD warnings + recommended allocation
  cashReservePct: number;      // 0..1 — fraction of capital kept as cash
  acceptedRiskWarning: boolean; // user has explicitly accepted the risk disclosure
  numHoldings: number | "auto"; // override max holding count; "auto" = derive from capital
  buyBandPct: number;          // tolerance band around yesterday close (e.g. 0.03 = ±3%)
  mode: Mode;                  // beginner = simplified UI, expert = full features
  theme: Theme;                // notion = light/friendly, trading = pure black/sharp
}

const DEFAULT: Profile = {
  capital: 0,
  riskTolerance: "medium",
  cashReservePct: 0.2,
  acceptedRiskWarning: false,
  numHoldings: "auto",
  buyBandPct: 0.03,
  mode: "beginner",
  theme: "notion",
};

// A-share constraint: minimum lot = 100 shares. Sized so user can fit at
// least ~100 shares of a median CSI300 stock (median close ~ ¥15-20).
export const MIN_PER_HOLDING = 2000;
export const MIN_CAPITAL = 10000;
export const MAX_HOLDINGS = 50;

export function deriveHoldingCount(capital: number, cashReserve: number): number {
  const invested = capital * (1 - cashReserve);
  if (invested < MIN_PER_HOLDING) return 1;
  return Math.min(MAX_HOLDINGS, Math.max(1, Math.floor(invested / MIN_PER_HOLDING)));
}

const KEY = "jr.profile";

export function loadProfile(): Profile {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT };
    return { ...DEFAULT, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT };
  }
}

export function saveProfile(p: Profile) {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
    // Notify listeners on the same window
    window.dispatchEvent(new CustomEvent("jr-profile-changed"));
  } catch {
    /* ignore */
  }
}

export function useProfile(): [Profile, (next: Partial<Profile>) => void] {
  const [p, setP] = useState<Profile>(loadProfile);
  useEffect(() => {
    const handler = () => setP(loadProfile());
    window.addEventListener("jr-profile-changed", handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener("jr-profile-changed", handler);
      window.removeEventListener("storage", handler);
    };
  }, []);
  const update = (next: Partial<Profile>) => {
    const merged = { ...p, ...next };
    saveProfile(merged);
    setP(merged);
  };
  return [p, update];
}

// --- Risk model ----------------------------------------------------------

export const RISK_PROFILE: Record<Risk, {
  label: string;
  description: string;
  // Drawdown the user should plan for (worst-case bear scenario)
  expectedMaxDD: number;
  // Suggested capital share to put into the strategy
  suggestedAllocation: number;
}> = {
  low: {
    label: "保守",
    description: "我不能接受本金亏损超过 10%。",
    expectedMaxDD: 0.25,           // strategy could draw down 25% in a bear
    suggestedAllocation: 0.25,     // → invest at most 25% of capital
  },
  medium: {
    label: "稳健",
    description: "我能接受短期亏损 20% 左右，长期想跑赢沪深300。",
    expectedMaxDD: 0.30,
    suggestedAllocation: 0.50,
  },
  high: {
    label: "激进",
    description: "我接受可能亏 30%+，追求更高超额收益。",
    expectedMaxDD: 0.40,
    suggestedAllocation: 0.80,
  },
};

export function fmtMoney(n: number): string {
  if (!Number.isFinite(n) || n === 0) return "¥0";
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${n >= 0 ? "" : "-"}¥${(abs / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${n >= 0 ? "" : "-"}¥${(abs / 1e4).toFixed(2)}万`;
  return `${n >= 0 ? "" : "-"}¥${abs.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}
