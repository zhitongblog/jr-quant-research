# jr-dashboard

A-share 量化研究月度 paper-trade 桌面应用。

## 运行方式

### 终端用户（不开发，只用）

直接装编译好的安装包：

- **MSI**: `frontend/src-tauri/target/release/bundle/msi/jr-dashboard_0.1.0_x64_en-US.msi`
- **NSIS**: `frontend/src-tauri/target/release/bundle/nsis/jr-dashboard_0.1.0_x64-setup.exe`

装完从开始菜单启动。

**注意**：当前 dashboard 默认读取 `D:/PM/jr/` 下的数据。给别人用之前需要：
- 让他们把 `D:/PM/jr/` 整个项目拷过去（含 `qlib_data/`, `paper_trades/`, `scripts/`），或
- 修改 `api/main.py` 中的 `JR_PROJ_ROOT` 默认值，或
- 通过环境变量 `JR_PROJ_ROOT` 启动

### 开发者（改代码 + 调试）

#### 浏览器模式（最快，不编译 Rust）

```cmd
desktop\start_dev.bat
```

自动启动 FastAPI (:8765) + Vite (:1420)，浏览器打开 dashboard。

#### Tauri 原生窗口模式（首次编译 5-10 分钟）

```bash
cd desktop/frontend
npm run tauri:dev
```

Rust 编译完后会弹出原生窗口。

#### 重新打包

```bash
# 1. 后端 sidecar 改了 → 重打 PyInstaller
cd desktop/api
D:/PM/jr/.venv/Scripts/python.exe -m PyInstaller jr_api.spec --noconfirm --clean

# 2. 前端 + Rust + 重新打 MSI/NSIS
cd desktop/frontend
npm run tauri:build
```

## 架构

```
+-------------------------------------+
|  Tauri Shell (Rust)                 |
|  - 启动时 spawn FastAPI sidecar     |
|  - 关闭时 kill sidecar              |
|  - 加载 WebView 显示 React 前端     |
+----+------------+-------------------+
     |            |
     v            v
+----------+   +-----------------------------+
|  React   |   |  FastAPI (PyInstaller exe)  |
|  Vite    |   |  - 读 qlib_data/CSV         |
|  dist/   |   |  - 读 paper_trades/JSON     |
+----+-----+   |  - 调 subprocess paper_     |
     |         |    trade_monthly.py         |
     |         +-----------------------------+
     |                       ^
     +--------- HTTP 8765 ---+
```

## 文件布局

```
desktop/
├── README.md               (this file)
├── start_dev.py            (dev-mode launcher: FastAPI + Vite + browser)
├── start_dev.bat           (双击启动 dev 模式)
├── generate_icon.py        (regenerate app icon source)
├── icon-source.png         (512x512 source for Tauri icon CLI)
├── api/
│   ├── main.py             (FastAPI app — 9 endpoints)
│   ├── jr_api.spec         (PyInstaller spec)
│   ├── build/              (PyInstaller build artifacts — gitignore)
│   └── dist/jr-api/        (PyInstaller output, 245MB)
└── frontend/
    ├── src/
    │   ├── api.ts          (FastAPI client + types)
    │   ├── App.tsx
    │   ├── components/
    │   │   ├── Card.tsx, Sidebar.tsx, TopBar.tsx, HoldingsTable.tsx
    │   └── views/
    │       ├── Portfolio.tsx     (latest holdings + LLM analysis)
    │       ├── Backtest.tsx      (v2/v3/v4/v5 vs benchmark)
    │       ├── Performance.tsx   (cumulative curves + monthly table)
    │       ├── History.tsx       (browse past predictions)
    │       └── Settings.tsx      (API base / paths / schedule)
    ├── src-tauri/
    │   ├── src/lib.rs      (spawn + kill sidecar)
    │   ├── tauri.conf.json (window + bundle config)
    │   ├── Cargo.toml
    │   └── icons/          (all generated app icons)
    ├── package.json
    └── vite.config.ts
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | /api/health | 健康检查 + 数据路径状态 |
| GET  | /api/portfolio/latest | 最新组合 + 中文名 + 行业 |
| GET  | /api/portfolio/history | 历史组合日期列表 |
| GET  | /api/portfolio/{date} | 指定日期的组合 |
| GET  | /api/llm/latest | 最新 LLM 行业 picks + macro_view |
| GET  | /api/backtest/comparison | v2/v3/v4/v5 横向对比 |
| GET  | /api/performance/timeseries | ensemble_evaluation.csv 解析 |
| POST | /api/run/monthly_update | 触发月度更新（async） |
| GET  | /api/run/status/{task_id} | 月度更新进度 + 日志尾巴 |

## 还能改进的（待办）

- **shadcn/ui**: 当前手写了 Card/Pill 等，可以换成 shadcn 提升观感
- **设置页扩展**: 加 DeepSeek API key 配置（当前从 `D:/PM/jr/.env` 读）
- **代码签名**: MSI 没签名，Windows SmartScreen 会警告。需要 code-signing cert
- **跨用户 portability**: `JR_PROJ_ROOT` 改成首次启动向导 + 配置文件
- **i18n 英文**: 当前全中文，可加英文切换
- **更多图表**: 持仓行业分布饼图、回测曲线对比图等
- **月度更新调度**: 应用内任务计划注册（当前只在 Settings 页提供 PowerShell 命令）

## 调试小贴士

- FastAPI 日志在 Tauri 进程 stdout（dev 模式终端可见）
- Tauri 自身日志通过 `tauri_plugin_log` 输出
- 改完前端立即生效（Vite HMR）
- 改完 FastAPI 需要重启 Tauri（dev 模式：Ctrl+C 后 `npm run tauri:dev`）
- 改完 Rust 需要等 Cargo 编译（dev 模式自动）
