# jr · A股量化研究 + paper-trading 桌面应用

<p align="center">
  <strong>多路径策略 · 月度调仓 · 桌面端可视化</strong><br>
  <em>本系统不构成投资建议。仅作研究和学习用途。</em>
</p>

<p align="center">
  <a href="https://github.com/zhitongblog/jr-quant-research/releases/latest">
    <img alt="release" src="https://img.shields.io/github/v/release/zhitongblog/jr-quant-research?color=00bcd4">
  </a>
  <img alt="python" src="https://img.shields.io/badge/python-3.11-blue">
  <img alt="tauri" src="https://img.shields.io/badge/tauri-2.x-orange">
  <img alt="react" src="https://img.shields.io/badge/react-19-61dafb">
  <img alt="platform" src="https://img.shields.io/badge/platform-Windows-lightgrey">
</p>

---

## 这是什么

一套面向 **A 股个人投资者** 的量化研究系统。

- 📊 **后端**：4 路径策略（量价反转 / 行业相对 / 基本面 / LLM 行业分析），月度调仓，已用 PBO 验证因子非过拟合
- 🖥 **前端**：Tauri 桌面应用，新手 / 专业双模式，可视化推荐、买入区间、K 线、行业排名、绩效追踪
- 🤖 **AI 集成**：DeepSeek-V4-Pro 月度行业宏观判断 + 财新新闻聚合上下文注入
- 📒 **交易管理**：手动录入或券商 CSV 导入交易，自动算真实持仓 + 盈亏 vs 沪深 300

历史回测在 2025-07 ~ 2026-05 单边牛市上达到 **Sharpe 2.58 / 累计 +33.15% / 最大回撤 -5.97%**，相对 CSI300 超额 +6.16pp。**仅一段牛市数据**，熊市表现未知，所以系统强制 paper-trading 6 个月再考虑实盘。

## 这不是什么

- ❌ 不是保证赚钱的工具
- ❌ 不是程序化交易客户端（A 股零售合规无法直连券商 API，只能手动下单 + 录入回流）
- ❌ 不是日内交易工具（数据日终更新，月度调仓）
- ❌ 不替你做投资决策（必须读完仓库 + Dashboard 内的所有"必读"才能开始）

## 安装

### 一般用户（双击即用）

去 [Releases](https://github.com/zhitongblog/jr-quant-research/releases/latest) 下载：

| 文件 | 大小 | 说明 |
|---|---:|---|
| `jr-dashboard-0.1.0-setup.exe` | 85 MB | **推荐**。NSIS 安装无须管理员 |
| `jr-dashboard-0.1.0-x64.msi` | 117 MB | MSI 安装，企业部署 |

⚠️ Windows SmartScreen 会警告"未识别的应用"（未代码签名）—— 选 "更多信息 → 仍要运行"

### 配置（首次必做）

1. 启动后进 **设置** 页
2. 填本金（建议 ≥¥10000）、风险等级、勾选风险声明
3. 填入你自己的 **DeepSeek API key**（[platform.deepseek.com](https://platform.deepseek.com/) 申请，1 元起充值）
4. 默认数据路径 `D:/PM/jr/`，可通过环境变量 `JR_PROJ_ROOT` 改

### 开发者（从源码跑）

需要：Python 3.11、Node 24+、Rust 1.77+、Tauri CLI

```bash
git clone https://github.com/zhitongblog/jr-quant-research.git
cd jr-quant-research

# Python 后端
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt  # TODO: 需要补这个文件
cp .env.example .env             # 然后填入你自己的 key

# 拉数据（需 30 分钟）
python scripts/cn_collector.py
python scripts/pull_industry_fundamentals.py

# 开发模式启动 dashboard
cd desktop
start_dev.bat                    # 一键启动 FastAPI + Vite
# 或：cd frontend && npm run tauri:dev (Tauri 原生窗口，首次 Rust 编译需 5-10 分钟)
```

## 4 路径策略对比 (2025-07 ~ 2026-05 单边牛市 OOS)

| 策略 | 累计收益 | Sharpe | 最大回撤 | 结论 |
|---|---:|---:|---:|---|
| **Path A** 行业-LGB | **+33.15%** | **+2.58** | **-5.97%** | ✅ 主力（行业相对反转 + 行业 categorical 特征） |
| Path B 行业轮动 | -1.33% ~ +22.7% | -0.04 ~ +1.92 | -8% | ❌ 牛市方向反了，留代码备震荡市 |
| Path C 加基本面 | +28.77% | +1.99 | -9.21% | ⚠️ 比 A 弱，月度 horizon 基本面是噪声 |
| Path D LLM 行业 | (paper) | (paper) | (paper) | ✅ 互补，与 A 交集仅 ~4，分散度高 |
| **Ensemble** A∩D + A 补齐 | (主推) | (主推) | (主推) | ✅ 给一般用户的默认 |
| CSI300 buy & hold | +26.99% | +2.00 | -7.78% | β 基准 |
| 等权 universe | +24.64% | +1.93 | -7.85% | α 检验基线 |

## 架构概览

```
┌────────────────────────────────────────────────────────┐
│   Tauri Shell (Rust) — 启动 sidecar / kill on exit     │
└────────────┬───────────────────────┬───────────────────┘
             │                       │
       ┌─────▼─────┐         ┌───────▼────────────┐
       │  React UI │  HTTP   │  FastAPI sidecar   │
       │  Vite     ├────────►│  (PyInstaller exe) │
       │  Tailwind │         │  17 endpoints      │
       └───────────┘         └────────┬───────────┘
                                       │ 触发月度更新 / 新闻刷新
                                       ▼
                              ┌────────────────────┐
                              │  scripts/ subproc  │
                              │  Qlib + LightGBM   │
                              │  + akshare         │
                              │  + DeepSeek API    │
                              └────────────────────┘
```

**数据流**：

1. `cn_collector.py` → akshare 拉 CSI300 日线 → `qlib_data/csv/*.csv`
2. `pull_industry_fundamentals.py` → 申万行业 + 基本面 → `qlib_data/sw1_idx/`、`qlib_data/fundamentals/`
3. `paper_trade_monthly.py` → 训 LGB + 调 LLM → `paper_trades/portfolio_*.json`
4. Dashboard 读 portfolio_*.json + my_trades.jsonl → 渲染推荐 + 实际持仓
5. 用户实际下单后回来录入 → 系统计算真实盈亏 vs 沪深 300

## 核心文档

- [`dist/README.md`](dist/README.md) — 安装包说明
- [`desktop/README.md`](desktop/README.md) — 桌面端架构 + 开发指南
- [`.env.example`](.env.example) — 环境变量模板

## 已知限制

1. **未代码签名** → Windows 安装会有 SmartScreen 警告
2. **数据非实时** → 日终（EOD），手动 `cn_collector.py` 才更新
3. **A 股零售无 API 下单** → 必须人工执行操作 + 录入回流
4. **模型只在牛市验证过** → 6 个月 paper-trading 后再考虑实盘
5. **DeepSeek API 必填** → LLM 行业分析依赖，否则 Path D 失效（其余功能不受影响）

## 路线图

- [ ] 实盘前再跑 6 个月 paper-trading 验证（关键！）
- [ ] 修生存偏差后的 Path B 在熊市的表现回测
- [ ] CSV 导入支持更多券商格式（当前覆盖东方财富 / 华泰 / 国信 / 同花顺）
- [ ] 用户自定义因子（pluggable 因子库）
- [ ] 多用户配置 / 团队共享 portfolio

## 反馈

- Bug / 改进意见：[Issues](https://github.com/zhitongblog/jr-quant-research/issues)
- 量化讨论：欢迎 PR / Discussion

## 致谢

- [Microsoft Qlib](https://github.com/microsoft/qlib) — 量化研究框架
- [akshare](https://github.com/akfamily/akshare) — A 股数据
- [Tauri](https://tauri.app/) — 桌面应用
- [DeepSeek](https://platform.deepseek.com/) — LLM 行业判断

## 免责声明

本系统**不构成任何投资建议**。所有策略和数据仅用于研究和学习。任何根据本系统建议的实盘投资**风险自担**。开发者不对任何使用本系统导致的投资亏损负责。
