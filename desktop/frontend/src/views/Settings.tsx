import { useEffect, useState } from "react";
import { api, getApiBase, setApiBase, type Health, type SecretsStatus } from "@/api";
import { Card, CardBody, CardHeader, Pill } from "@/components/Card";
import { useProfile, RISK_PROFILE, fmtMoney, MIN_CAPITAL } from "@/profile";

export function SettingsView({ refreshKey }: { refreshKey: number }) {
  const [profile, updateProfile] = useProfile();
  const [capitalInput, setCapitalInput] = useState(profile.capital.toString());
  const [apiBaseInput, setApiBaseInput] = useState(getApiBase());
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);

  const probe = () => {
    setError(null);
    api.health()
      .then(setHealth)
      .catch((e) => { setHealth(null); setError(String(e)); });
  };

  useEffect(probe, [refreshKey]);

  const saveCapital = () => {
    const c = Number(capitalInput.replace(/[^0-9.]/g, ""));
    if (!Number.isFinite(c) || c < 0) return;
    updateProfile({ capital: c });
    setSavedNotice("本金已保存");
    setTimeout(() => setSavedNotice(null), 1500);
  };

  const saveApi = () => {
    setApiBase(apiBaseInput);
    setSavedNotice("API base 已保存");
    probe();
    setTimeout(() => setSavedNotice(null), 1500);
  };

  return (
    <div className="p-6 space-y-6 overflow-auto max-w-3xl">
      <h1 className="text-2xl font-semibold text-fg">设置</h1>

      <Card>
        <CardHeader
          title="① 本金与风险"
          subtitle="dashboard 用这两项算操作单 + 风险预警，必填"
          right={profile.capital > 0 && profile.acceptedRiskWarning
            ? <Pill tone="up">已完成</Pill>
            : <Pill tone="down">待完成</Pill>
          }
        />
        <CardBody className="space-y-5">
          <div>
            <label className="text-xs text-muted mb-1.5 block">本金（元）</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={capitalInput}
                onChange={(e) => setCapitalInput(e.target.value)}
                placeholder="例如 100000"
                className="flex-1 px-3 py-1.5 bg-panel-2 border border-border rounded-md text-sm font-mono focus:outline-none focus:border-accent/60"
              />
              <button
                type="button"
                onClick={saveCapital}
                className="px-4 py-1.5 rounded-md bg-accent/15 hover:bg-accent/25 text-accent border border-accent/40 text-sm"
              >
                保存
              </button>
            </div>
            <div className="text-[11px] mt-1 flex items-center gap-2">
              <span className="text-muted">当前 {fmtMoney(profile.capital)}</span>
              {profile.capital > 0 && profile.capital < MIN_CAPITAL && (
                <span className="text-down">
                  ⚠️ 低于建议最小 {fmtMoney(MIN_CAPITAL)}（A 股 100 股一手限制下下不了几只单）
                </span>
              )}
              <span className="text-muted">· 不要把房贷/教育金/应急金算进来</span>
            </div>
          </div>

          <div>
            <label className="text-xs text-muted mb-1.5 block">风险承受度</label>
            <div className="grid grid-cols-3 gap-2">
              {(["low", "medium", "high"] as const).map((k) => {
                const r = RISK_PROFILE[k];
                return (
                  <button
                    key={k}
                    type="button"
                    onClick={() => updateProfile({ riskTolerance: k })}
                    className={`text-left px-3 py-2 rounded-md border transition ${
                      profile.riskTolerance === k
                        ? "bg-accent/10 border-accent/40"
                        : "bg-panel-2 border-border hover:border-accent/30"
                    }`}
                  >
                    <div className={`text-sm font-medium ${
                      profile.riskTolerance === k ? "text-accent" : "text-fg"
                    }`}>
                      {r.label}
                    </div>
                    <div className="text-xs text-muted mt-1 leading-relaxed">{r.description}</div>
                    <div className="text-[10px] text-muted mt-2">
                      预期最坏回撤 -{(r.expectedMaxDD * 100).toFixed(0)}% · 建议投入 {(r.suggestedAllocation * 100).toFixed(0)}%
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="text-xs text-muted mb-1.5 block">
              现金保留比例：<span className="text-fg font-mono">{(profile.cashReservePct * 100).toFixed(0)}%</span>
            </label>
            <input
              type="range"
              min="0" max="0.5" step="0.05"
              value={profile.cashReservePct}
              onChange={(e) => updateProfile({ cashReservePct: Number(e.target.value) })}
              className="w-full accent-accent"
            />
            <div className="text-[11px] text-muted mt-1">
              剩余现金可对冲回撤期间的补仓机会，0% = 满仓
            </div>
          </div>

          <div className={`border-2 rounded-md p-3 transition-all ${
            profile.acceptedRiskWarning
              ? "border-up/30 bg-up/5"
              : "border-down/50 bg-down/5 animate-pulse"
          }`}>
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={profile.acceptedRiskWarning}
                onChange={(e) => updateProfile({ acceptedRiskWarning: e.target.checked })}
                className="mt-0.5 w-5 h-5 accent-accent cursor-pointer"
              />
              <div className="text-xs text-fg/90 leading-relaxed">
                <div className="font-medium text-fg mb-1">
                  {profile.acceptedRiskWarning ? "✓ 已确认风险声明" : "⚠️ 必读：请勾选确认"}
                </div>
                我已阅读并理解：本系统<strong className="text-down">不是投资建议</strong>，仅作研究工具。
                历史回测仅在单边牛市验证，熊市可能 -30%+。我接受所有亏损风险，
                不把生活必需资金投入。
              </div>
            </label>
          </div>

          {savedNotice && <div className="text-xs text-up">✓ {savedNotice}</div>}
        </CardBody>
      </Card>

      <DeepseekKeyCard />

      <Card>
        <CardHeader
          title="② 后端 API"
          subtitle="FastAPI 服务地址。本地通常是 127.0.0.1:8765"
          right={health ? <Pill tone="up">已连接</Pill> : <Pill tone="down">未连接</Pill>}
        />
        <CardBody className="space-y-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={apiBaseInput}
              onChange={(e) => setApiBaseInput(e.target.value)}
              placeholder="http://127.0.0.1:8765"
              className="flex-1 px-3 py-1.5 bg-panel-2 border border-border rounded-md text-sm font-mono focus:outline-none focus:border-accent/60"
            />
            <button type="button" onClick={saveApi}
              className="px-4 py-1.5 rounded-md bg-accent/15 hover:bg-accent/25 text-accent border border-accent/40 text-sm">
              保存并测试
            </button>
          </div>
          {error && <div className="text-xs text-down break-all">{error}</div>}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="③ 数据路径状态" subtitle="后端报告的本地数据位置" />
        <CardBody>
          {!health ? (
            <div className="text-sm text-muted">连接后端后才能查看。</div>
          ) : (
            <div className="space-y-2 text-sm font-mono">
              <Row label="项目根目录" value={health.proj_root} />
              <Row label="qlib_data/ 存在" value={String(health.qlib_data_exists)}
                tone={health.qlib_data_exists ? "up" : "down"} />
              <Row label="paper_trades/ 存在" value={String(health.paper_trades_exists)}
                tone={health.paper_trades_exists ? "up" : "down"} />
              <Row label="历史组合快照" value={`${health.n_portfolios}`} />
              <Row label="历史 LLM 预测" value={`${health.n_predictions}`} />
              <Row label="服务器时间" value={health.server_time} />
            </div>
          )}
          <div className="mt-4 text-xs text-muted leading-relaxed">
            提示：环境变量 <code className="font-mono bg-panel-2 px-1.5 py-0.5 rounded mx-1">JR_PROJ_ROOT</code> 可改数据路径，
            <code className="font-mono bg-panel-2 px-1.5 py-0.5 rounded mx-1">JR_API_PORT</code> 改端口（默认 8765）。
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="④ 月度自动调度" />
        <CardBody>
          <div className="text-sm text-muted leading-relaxed space-y-2">
            <p>用 Windows 任务计划程序（管理员 PowerShell）：</p>
            <pre className="bg-panel-2 border border-border rounded p-3 font-mono text-xs overflow-x-auto">{`$action = New-ScheduledTaskAction \`
  -Execute "D:\\PM\\jr\\.venv\\Scripts\\python.exe" \`
  -Argument "D:\\PM\\jr\\scripts\\paper_trade_monthly.py" \`
  -WorkingDirectory "D:\\PM\\jr"
$trigger = New-ScheduledTaskTrigger -Monthly -At "09:00am" -DaysOfMonth 1
Register-ScheduledTask -TaskName "jr_paper_trade_monthly" \`
  -Action $action -Trigger $trigger -RunLevel Highest`}</pre>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function DeepseekKeyCard() {
  const [status, setStatus] = useState<SecretsStatus | null>(null);
  const [key, setKey] = useState("");
  const [model, setModel] = useState("deepseek-v4-pro");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const reload = () => { api.secretsStatus().then(setStatus).catch(() => setStatus(null)); };
  useEffect(() => { reload(); }, []);

  const save = async () => {
    setMsg(null);
    if (!key.trim()) { setMsg({ kind: "err", text: "请填 API key" }); return; }
    if (!key.startsWith("sk-")) { setMsg({ kind: "err", text: "DeepSeek key 一般以 sk- 开头" }); return; }
    setBusy(true);
    try {
      await api.setDeepseek(key.trim(), model.trim() || "deepseek-v4-pro");
      setMsg({ kind: "ok", text: "✓ 已保存到本机 secrets.json" });
      setKey(""); // clear input for safety
      reload();
    } catch (e) {
      setMsg({ kind: "err", text: String(e) });
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    if (!window.confirm("确定清除已保存的 DeepSeek key？\n清除后 LLM 行业分析功能将无法使用。")) return;
    try {
      await api.clearDeepseek();
      reload();
    } catch (e) {
      alert(String(e));
    }
  };

  return (
    <Card>
      <CardHeader
        title="DeepSeek API key（LLM 行业分析必填）"
        subtitle="从 https://platform.deepseek.com 申请。每个用户用自己的 key——key 仅保存到本机 paper_trades/secrets.json，永不上传任何地方。"
        right={status?.deepseek_set
          ? <Pill tone="up">已配置</Pill>
          : <Pill tone="down">未配置</Pill>
        }
      />
      <CardBody className="space-y-3">
        {status?.deepseek_set ? (
          <div className="space-y-2">
            <div className="text-sm">
              <span className="text-muted">已保存 key：</span>
              <code className="font-mono text-fg bg-panel-2 px-2 py-0.5 rounded ml-2">
                {status.deepseek_key_preview}
              </code>
            </div>
            <div className="text-sm">
              <span className="text-muted">模型：</span>
              <code className="font-mono text-fg bg-panel-2 px-2 py-0.5 rounded ml-2">
                {status.deepseek_model || "deepseek-v4-pro"}
              </code>
            </div>
            <div className="flex gap-2 pt-2">
              <button type="button" onClick={() => setStatus(null)}
                className="px-3 py-1.5 rounded bg-panel-2 hover:bg-panel-2/80 text-fg border border-border text-sm">
                重新设置
              </button>
              <button type="button" onClick={clear}
                className="px-3 py-1.5 rounded bg-down/10 hover:bg-down/20 text-down border border-down/30 text-sm">
                清除
              </button>
            </div>
          </div>
        ) : (
          <>
            <div>
              <label className="text-xs text-muted mb-1.5 block">API key</label>
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                className="w-full px-3 py-1.5 bg-panel-2 border border-border rounded-md text-sm font-mono focus:outline-none focus:border-accent/60"
              />
              <div className="text-[11px] text-muted mt-1">
                没有 key？去 <span className="text-accent">platform.deepseek.com</span> 注册（充 1 元就能用，每次月度更新约 ¥0.05 成本）
              </div>
            </div>
            <div>
              <label className="text-xs text-muted mb-1.5 block">模型</label>
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="deepseek-v4-pro"
                className="w-full px-3 py-1.5 bg-panel-2 border border-border rounded-md text-sm font-mono focus:outline-none focus:border-accent/60"
              />
            </div>
            <div className="flex justify-end">
              <button type="button" onClick={save} disabled={busy}
                className="px-4 py-1.5 rounded-md bg-accent/15 hover:bg-accent/25 text-accent border border-accent/40 text-sm disabled:opacity-40">
                {busy ? "保存中..." : "保存到本机"}
              </button>
            </div>
          </>
        )}
        {msg && (
          <div className={`text-xs ${msg.kind === "ok" ? "text-up" : "text-down"}`}>
            {msg.text}
          </div>
        )}
        <div className="text-[11px] text-muted leading-relaxed pt-2 border-t border-border/40">
          🔒 <strong className="text-fg">隐私</strong>：key 只写本机 <code className="font-mono bg-panel-2 px-1 rounded">paper_trades/secrets.json</code>，
          不会出现在 GitHub、备份或任何远程位置。卸载时手动删除该文件即可彻底清除。
        </div>
      </CardBody>
    </Card>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  const cls = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-fg";
  return (
    <div className="flex justify-between border-b border-border/30 py-1.5">
      <span className="text-muted">{label}</span>
      <span className={cls}>{value}</span>
    </div>
  );
}
