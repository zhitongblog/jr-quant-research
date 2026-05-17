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

## 系统要求

按使用场景三档：

### 1️⃣ 只装 dashboard 看推荐（终端用户）
| 项 | 最低 | 推荐 |
|---|---|---|
| OS | Windows 10 x64 | Windows 11 |
| RAM | 4 GB | 8 GB |
| 硬盘 | 250 MB | 500 MB |
| Python | **不需要装** | — |
| DeepSeek API key | 可选 | 必填（LLM 行业分析依赖） |

→ 这就是发给朋友的版本，安装包从 Releases 下载即可。

### 2️⃣ 跑数据 + 训模型（开发者）
| 项 | 最低 | 推荐 |
|---|---|---|
| RAM | **16 GB** | **32 GB** |
| 硬盘 | 5 GB | 20 GB |
| CPU | i5 / Ryzen 5 | i7 / Ryzen 7+ |
| Python | **3.11.x** | 3.11.x (qlib 不支持 3.12) |
| 网络 | **国内 IP** | 国内 IP（akshare 走新浪/百度，海外 IP 数据不全） |

→ LightGBM 训 463k 行 × 100+ 特征 ~6 GB；月度策略全跑 5-15 分钟；数据采集 30-60 分钟。

### 3️⃣ 本地 LLM 替代 DeepSeek（可选）
- 显存 12 GB+（qwen2.5-coder:14b Q4_K_M 占 9 GB）
- **不推荐**：实测 R1 在 Qlib DSL 上写错率高，qwen2.5-coder 慢 5 倍。付费 ¥1-5/月 API 更划算

### 网络坑（必读）
- **不要开 Clash/V2Ray 走 akshare** — 海外 IP 403 或数据不全
- 设 `NO_PROXY=*`（`.env.example` 已写）
- DeepSeek API 是国内域名，不受代理影响

---

## 方法论 / 我们做了什么

这套系统不是"凭感觉乱跑"，所有策略都经过**学术界标准的验证步骤**。

### 数据
- **A 股 CSI300 全量日线**（2018-01-02 ~ 2026-05-15）：akshare 拉新浪后端，避免 eastmoney TLS 指纹封 IP
- **生存偏差修正**：用 baostock 拉每月成分股快照（600 个区间），重建动态成分股表。**修正前 Alpha158 baseline +22.7%，修正后 -9%——31pp 缩水。** 没修过的回测结果都是水分
- **PIT (point-in-time) 严格**：财务数据 90 天发布延迟（年报 4-30 才公布，季报 1 个月后），merge_asof 单调对齐，杜绝未来函数

### 因子
4 个验证过的因子（不是随便堆 158 个）：

| 因子 | 表达式 | RankIC | PBO |
|---|---|---:|---:|
| `limit_up_reversal_20d` | `0 - Mean(Greater($close/Ref($close,1)-1, 0.095), 20)` | **+0.0209** (W=30) | **0.42** ✅ |
| `price_volume_divergence` | `(vol - mean20)/std20 * ret1` | +0.0168 | — |
| `amihud_illiquidity_20d` | `Mean(|ret1|/$amount, 20)` | -0.0124 | — |
| 行业相对版本 | `factor - industry_mean(factor)` | LGB 最强特征 (imp 1350) | — |

**关键证据：limit_up_reversal_20d PBO = 0.42 < 0.5**

PBO (Probability of Backtest Overfitting, Bailey 2014) 是判断回测是否过拟合的金标准。我们跑了 35 个参数变体（7 个窗口 × 5 个阈值），所有 RankIC 都是正数（+0.0065 ~ +0.0209），CSCV 16 折切片 PBO=0.42——**远低于 0.5 阈值**。对照组：LightGBM + Alpha158 (158 个因子) PBO=0.75，严重过拟合。

简单说：我们的因子**经得起参数扰动**，不是"恰好这个值才赚钱"的曲线拟合。

### 模型
- **LightGBM 月度回归**（不是 deep learning 黑盒）
  - 训练：2018-01 ~ 2024-06（6.5 年）
  - 验证：2024-07 ~ 2025-06（1 年，早停 50 轮）
  - 测试 OOS：2025-07 ~ 2026-05（10 个月）
  - `best_iter=140`（健康学习深度，非欠拟合也非过拟合）
- **特征**：3 个基础因子 + 3 个行业相对版本 + sw1_cat（行业 categorical）

### 验证
1. **PBO** 验证因子稳定性（见上）
2. **CPCV** (Combinatorial Purged Cross-Validation, López de Prado 2018)：6 组 × 选 2 测试，embargo 1%
3. **Walk-forward** 滚动重训对比固定训练窗口
4. **vs 基准对比强制项**：每个策略变体都必须报告 vs CSI300 + 等权 universe。**这一步抓出了第一版 -10% 负 alpha 的乌龙**（误把 β 当 α）

| 策略 | 累计收益 | Sharpe | 最大回撤 | 结论 |
|---|---:|---:|---:|---|
| **Path A** 行业-LGB | **+33.15%** | **+2.58** | **-5.97%** | ✅ 主力（行业相对反转 + 行业 categorical 特征） |
| Path B 行业轮动 | -1.33% ~ +22.7% | -0.04 ~ +1.92 | -8% | ❌ 牛市方向反了，留代码备震荡市 |
| Path C 加基本面 | +28.77% | +1.99 | -9.21% | ⚠️ 比 A 弱，月度 horizon 基本面是噪声 |
| Path D LLM 行业 | (paper) | (paper) | (paper) | ✅ 互补，与 A 交集仅 ~4，分散度高 |
| **Ensemble** A∩D + A 补齐 | (主推) | (主推) | (主推) | ✅ 给一般用户的默认 |
| CSI300 buy & hold | +26.99% | +2.00 | -7.78% | β 基准 |
| 等权 universe | +24.64% | +1.93 | -7.85% | α 检验基线 |

### 实盘建议
- **paper-trade 6 个月**至少覆盖一次回调 → 看 ensemble 超额收益是否稳定 → 再考虑实盘
- 即使实盘也建议先**小仓位（≤25% 本金）**试探，按风险等级递增
- 永远配合 CSI300 ETF (510300) 定投做对冲

### 已知风险
1. **样本期单一**：10 个月 OOS 全在单边牛市，熊市/震荡市表现**未知**
2. **小本金分散不足**：A 股一手 100 股限制，¥10000 只能买 4-5 只，单票风险大
3. **行业暴露集中**：top-K 可能扎堆某一行业，需要 dashboard 行业分布图盯紧
4. **LLM 上下文有限**：DeepSeek 训练截止后的新事件不知道，需要用户手动输入"近况摘要"或刷新新闻
5. **A 股零售无 API 下单**：每月手动执行 + 录入回流，靠人为纪律
6. **未做交易成本压力测试**：默认 0.13% 买 / 0.18% 卖，若你券商佣金更高需要重算

---

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
