import { useCallback, useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { OverviewView } from "@/views/Overview";
import { BeginnerHome } from "@/views/BeginnerHome";
import { useProfile } from "@/profile";
import { TradeListView } from "@/views/TradeList";
import { MyTradesView } from "@/views/MyTrades";
import { PortfolioView } from "@/views/Portfolio";
import { NewsView } from "@/views/News";
import { BenchmarkView } from "@/views/Benchmark";
import { PerformanceView } from "@/views/Performance";
import { BacktestView } from "@/views/Backtest";
import { HistoryView } from "@/views/History";
import { SettingsView } from "@/views/Settings";
import { StockDetailView } from "@/views/StockDetail";

export type ViewKey =
  | "overview"
  | "trades"
  | "my_trades"
  | "portfolio"
  | "news"
  | "benchmark"
  | "performance"
  | "backtest"
  | "history"
  | "settings";

export default function App() {
  const [view, setView] = useState<ViewKey>("overview");
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [profile] = useProfile();
  const refresh = useCallback(() => setRefreshKey((x) => x + 1), []);
  const isBeginner = profile.mode === "beginner";

  const navigate = useCallback((k: ViewKey) => {
    setView(k);
    setSelectedSymbol(null);
  }, []);

  return (
    <div className="flex h-full">
      <Sidebar current={view} onChange={navigate} />
      <main className="flex-1 flex flex-col min-w-0">
        <TopBar onRefresh={refresh} />
        <div className="flex-1 min-h-0">
          {selectedSymbol ? (
            <StockDetailView
              symbol={selectedSymbol}
              onBack={() => setSelectedSymbol(null)}
              onSelectSymbol={setSelectedSymbol}
            />
          ) : (
            <>
              {view === "overview" && (
                isBeginner
                  ? <BeginnerHome refreshKey={refreshKey} onNavigate={navigate} onSelectSymbol={setSelectedSymbol} />
                  : <OverviewView refreshKey={refreshKey} onNavigate={navigate} />
              )}
              {view === "trades" && <TradeListView refreshKey={refreshKey} onSelectSymbol={setSelectedSymbol} />}
              {view === "my_trades" && <MyTradesView refreshKey={refreshKey} onSelectSymbol={setSelectedSymbol} />}
              {view === "portfolio" && <PortfolioView refreshKey={refreshKey} onSelectSymbol={setSelectedSymbol} />}
              {view === "news" && <NewsView refreshKey={refreshKey} />}
              {view === "benchmark" && <BenchmarkView refreshKey={refreshKey} />}
              {view === "performance" && <PerformanceView refreshKey={refreshKey} />}
              {view === "backtest" && <BacktestView refreshKey={refreshKey} />}
              {view === "history" && <HistoryView refreshKey={refreshKey} onSelectSymbol={setSelectedSymbol} />}
              {view === "settings" && <SettingsView refreshKey={refreshKey} />}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
