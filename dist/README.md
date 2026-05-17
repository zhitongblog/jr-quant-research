# jr-dashboard 安装包

A 股量化研究 paper-trading 桌面应用 v0.1.0 (Windows x64)

## 两种安装包，挑一个

| 文件 | 大小 | 推荐 |
|---|---:|---|
| `jr-dashboard-0.1.0-setup.exe` | 85 MB | **推荐**：NSIS 安装器，用户级安装无须管理员 |
| `jr-dashboard-0.1.0-x64.msi` | 117 MB | MSI 安装器，需管理员权限，企业部署友好 |

## 安装步骤

1. 双击 `.exe`（或 `.msi`）
2. Windows SmartScreen 会警告"未识别的应用"——选**"更多信息" → "仍要运行"**（未做代码签名）
3. 一路下一步，默认安装到 `%LOCALAPPDATA%\jr-dashboard`（NSIS）或 `C:\Program Files\jr-dashboard`（MSI）
4. 从开始菜单找 **"jr-dashboard"** 启动

## 首次启动会发生什么

1. Tauri 应用启动，会**自动启一个 FastAPI 后端进程**（端口 8765，本地 only）
2. 浏览器窗口里显示 dashboard
3. 默认是**新手模式**——只显示"本月推荐 / 我的交易 / 设置"3 项
4. 第一步必填本金 + 风险声明（在"设置"页）

## ⚠️ 重要：数据从哪来？

这个安装包**只装 UI 和后端 API 服务**，**不包含 A 股数据**。

- 后端默认读路径：`D:/PM/jr/qlib_data/` 和 `D:/PM/jr/paper_trades/`
- 大部分人机器上没有这些目录 → 启动后 dashboard 会显示 "数据缺失"

**解决办法**（按推荐顺序）：

### A. 设置环境变量，指向你自己的数据
```cmd
setx JR_PROJ_ROOT "D:\my-jr-data"
```
然后重启 jr-dashboard。要求该目录下有 `qlib_data/` 和 `paper_trades/` 两个子目录。

### B. 找开发者要演示数据包
约 30MB 的 zip，含：
- 31 个申万行业指数日线
- ~50 只 CSI300 个股 CSV（足够 demo 展示）
- 最新一期模型组合 + LLM 行业推荐

解压到 `D:\PM\jr\` 即可（保留默认路径）。

### C. 自己跑数据采集脚本（高级用户）
需要 Python 3.11 + 一个 venv，按项目 README.md 跑：
```cmd
python scripts\cn_collector.py
python scripts\pull_industry_fundamentals.py
```

## 卸载

- NSIS 版：`%LOCALAPPDATA%\jr-dashboard\uninstall.exe`，或控制面板 → 程序与功能
- MSI 版：控制面板 → 程序与功能 → 卸载

应用本身完全清理。Dashboard 写入的 `paper_trades/my_trades.jsonl`（交易记录）、`news_context.txt`（你的新闻摘要）保留在 `JR_PROJ_ROOT/paper_trades/`——卸载不会自动删，需手动清。

## 已知限制

1. **没有代码签名** → 第一次启动 Windows 会提示警告。生产分发需 ¥1500/年的代码签名证书
2. **数据更新只能手动** → 内置 "立即跑月度更新" 按钮要求本机有 Python venv，没装就用不了
3. **行情数据是日终（EOD）** → 看不到盘中实时价
4. **新闻自动聚合 + 立即跑月度更新** → 都需要本机 Python 环境，纯绿色用户只能用"我的交易"和"持仓查看"功能
5. **模型只在 2025-07 ~ 2026-05 单边牛市上验证过** → 不构成投资建议，实盘前必看"vs 沪深300"页诚实评估

## 反馈

- bug / 改进意见：直接联系开发者
- 重大不要：把本系统当成保证赚钱的工具。它只是研究产物。
