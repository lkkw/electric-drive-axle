# 株齿 2.5T 电驱桥下线测试上位机

Windows 桌面上位机：通过周立功 USBCAN 以 10 ms 周期向 MCU 下发 VCU_11 (0x258) 控制帧，
实时解码 MCU 反馈 (0x35A / 0x35B / 0x35C)，提供手动控制、后端循环工况测试、CAN 报文
监视与多层安全停机。后端为 FastAPI（REST + SSE），前端为 Vue 3 + shadcn/vue，最终由
PyWebView + PyInstaller 打包为单个 EXE。

通信矩阵与故障码依据仓库根目录的
`DFAC_Matrix_11898_CAN_DF_8_AMB2_V1.2_PCAN-0813_MCU.xlsx` 与
`DFAC 控制器故障代码-AMB2(2).xlsx`。

## 架构

```text
Vue 3 (Pinia / Alova / ECharts)  ──REST + SSE──▶  FastAPI  /api/v1/axle
                                                     │
                                             AxleManager (asyncio 单例)
                                 ┌───────────────┼──────────────────┐
                           10 ms TX 循环     5 ms RX 循环         循环测试状态机
                           (VCU_11 0x258)    解码 + 安全监控       (服务端单调时钟)
                                                     │
                                   ZlgCanDriver (ctypes + 线程池 + 调用超时)
                                                     │
                                             zlgcan.dll → USBCAN
```

## 目录结构

```text
electric-drive-axle/
├─ backend/
│  ├─ app/
│  │  ├─ core/can/            # zlgcan.dll 封装、信号编解码、常量与故障码表
│  │  ├─ core/config.py       # 环境变量配置（含数据目录）
│  │  ├─ routers/axle.py      # REST 接口与 SSE 遥测流
│  │  ├─ schemas/axle.py      # Pydantic 请求/响应/遥测模型
│  │  ├─ services/
│  │  │  ├─ axle_manager.py   # 连接生命周期、收发循环、急停、安全监控、循环测试
│  │  │  └─ safety_store.py   # 安全阈值 JSON 持久化
│  │  └─ main.py              # FastAPI 工厂（桌面模式下同时托管前端）
│  ├─ zlgcan_x64/             # 周立功 64 位驱动及 kerneldlls
│  ├─ tests/                  # pytest（使用模拟驱动，无需硬件）
│  ├─ main.py                 # 开发启动器 (uvicorn --reload, 端口 8000)
│  ├─ desktop.py              # PyWebView 桌面入口
│  └─ build.py                # 前端构建 + PyInstaller 打包
├─ frontend/
│  └─ src/
│     ├─ api/axle.ts          # Alova 接口方法
│     ├─ stores/useAxleStore.ts  # 遥测状态、SSE、曲线历史
│     ├─ composables/         # 循环测试编辑器等
│     ├─ components/axle/     # 控制卡、MCU 反馈卡、曲线、急停/故障弹窗
│     ├─ components/ui/       # shadcn/vue CLI 生成的组件源码
│     └─ views/               # 控制台 /axle、CAN 通信 /can、安全配置 /safety
├─ docs/技术文档.md            # 详细技术文档（架构、原理、维护指南）
├─ .agents/skills/shadcn-vue/  # 前端 UI 组件编写规范
└─ package_exe.bat            # 一键打包脚本
```

## PLC 自动上电 / 下电

“台架供电”页通过以太网连接西门子 S7-1500（python-snap7），读写 dbPC [DB40]（点表由 PLC 工程师提供），
产品编号固定 1、电压 340 V：

- **上电**：确认 Safe=1、电机未使能（急停互锁中也可上电，互锁期间电机无法使能）→ 写 Request_power=1 → 最长 30 s 等待上电完成与主接触器吸合；超时自动复位请求。
- **下电**：先关闭电机使能，再复位 Request_power，最长 5 s 确认接触器断开。
- **上传 MES**：PLC 连接后持续把电机实际转速 (rpm) 和电机温度 (℃) 写入 Speed / Temp（DBD14 / DBD18），值变化才写；CAN 未连接或反馈过期时写 0。
- PLC 地址默认 192.168.8.1（rack 0 / slot 1），可在页面修改并保存；支持本地仿真用于演练。
- 页面底部的“PLC 通信监视”实时显示双方点表，并按时间记录上位机每次写入（含来源）和 PLC 反馈的变化，联调时用来定位信号没对上的环节。

## 试车记录

- **判定**：下线测试页的“试车判定”卡片实时显示当前这台的试车统计（时长、最高转速、最大转矩、最高电机 / 控制器温度、最大母线电流、故障码、安全停机次数），操作员点“合格”或“NG”（可填备注）后：结果写入 PLC Result（DBW6，1=OK 2=NG）上传 MES，保存一条试车记录，统计清零开始下一台。PLC 未连接或写入失败时仍保存记录，并标记“未写入 PLC”。
- **自动判定**：循环测试跑完后自动判定并请求下电，不用手动点。合格标准：全部圈数正常跑完，且本轮循环期间没有故障码、没有急停 / 自动安全停机；否则判 NG。循环中途被急停、CAN 链路故障等异常中断也判 NG 并下电；操作员点“终止并归零”则不判定、不下电。流程是先等电机停转（最长 30 s），再写结果、保存记录（备注写明判定依据），最后下电，结论显示在循环测试面板上。循环执行中和自动判定期间，手动“合格 / NG”按钮不可用。
- **统计范围**：从上次判定后（或循环测试开始时）第一次收到 MCU 反馈开始累计；转速、转矩、电流取绝对值。序列号取 PLC 回传的 Sn。
- **查询**：侧边栏“试车记录”页按日期、序列号、结论筛选，显示合格率；可导出 CSV（Excel 直接打开），导出后自动打开所在文件夹。

## 安全机制

| 机制 | 触发条件 | 动作 |
|---|---|---|
| 手动急停 | 操作员点击“紧急停机” | 立即发送停机帧，进入急停互锁 |
| 越限自动停机 | 新鲜的 0x35B / 0x35C 反馈中转速、转矩（绝对值）或电机温度超过阈值 | 记录事件并进入急停互锁 |
| 反馈中断看门狗 | 使能期间 0x35B 超过 `feedback_timeout_ms`（默认 500 ms）未更新 | 记录事件并进入急停互锁 |
| 链路故障自动断开 | 电机已使能或循环测试未结束时，同一通道收/发驱动调用连续异常 10 次或持续 1 s | 结束循环测试、尽力发送停机帧、释放设备并上报 `link_error` |
| 总线无应答提示 | 空闲时（未使能、无循环测试）驱动调用异常，多为控制器未上电导致发送超时 | 保持连接，在 CAN 通讯页显示“控制器无应答”徽章（`bus_warning`）；恢复通信后自动消失 |
| PLC Safe 联锁 | 已请求上电或已通电时 PLC 安全回路断开（Safe=0） | 复位上电请求切断 340 V 高压，触发急停互锁 |
| 急停切高压 | 任何急停或 CAN 链路故障 | 立即复位 PLC 上电请求 |
| 断开/重连 | 操作员断开或重新连接 | 由 10 ms 循环连续发送两帧安全帧（Life 连续），等待旧任务退出后再释放句柄 |

急停互锁期间后端拒绝使能与任何非零控制量；复位只解除互锁，不恢复停机前的控制量。
紧急停机按钮常驻顶部栏，任何页面都可触发。软件急停不能替代台架硬件急停。

桌面程序同一时间只允许运行一个；电机已使能或循环测试未结束时关闭窗口会弹出确认，
确认后发送停机帧再断开 CAN。

## 数据与日志

数据目录默认为 `%APPDATA%\electric-drive-axle\`，可通过环境变量 `AXLE_DATA_DIR` 修改：

| 文件 | 内容 | 保留 |
|---|---|---|
| `safety_config.json` | 自动停机阈值，重启后自动恢复；损坏时回退默认值 | 永久 |
| `plc_config.json` | PLC 连接参数（IP、机架、槽号、仿真） | 永久 |
| `test_records.db` | 试车记录（SQLite） | 永久 |
| `exports\` | 导出的试车记录 CSV | 永久 |
| `logs\app.log` | 全部运行日志（含驱动异常、未捕获异常） | 按天轮转，30 天 |
| `logs\events.log` | 连接/断开、急停与复位、自动停机、链路故障、循环测试、安全配置变更 | 按天轮转，365 天 |

`zlgcan.dll` 加载失败时程序仍会启动，CAN 通讯页显示失败原因并禁用连接按钮。

## 版本号

唯一来源为 `backend/app/__init__.py` 的 `__version__`，`backend/pyproject.toml` 与
`frontend/package.json` 必须同步修改（测试会校验）。版本号与构建时间显示在左下角“软件信息”中。

## 环境要求

- Windows 10/11 x64（`zlgcan.dll` 仅支持 Windows）
- Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)
- Node.js `^20.19.0 || >=22.12.0` 与 pnpm 11+
- 目标电脑需安装 Microsoft Edge WebView2 Runtime（桌面窗口）

## 本地开发

后端：

```powershell
cd backend
uv sync
uv run main.py
```

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

前端（另开一个终端）：

```powershell
cd frontend
pnpm install
pnpm dev
```

浏览器访问 <http://127.0.0.1:5173>，Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 检查命令

```powershell
cd backend
uv run pytest
uv run ruff check .
```

```powershell
cd frontend
pnpm type-check
pnpm test
pnpm build
```

## 打包 Windows 桌面 EXE

直接运行根目录的 `package_exe.bat` 即可交互式选择单文件或目录模式。手动执行：

```powershell
cd backend
uv sync --group desktop
# 目录模式 + 控制台日志，适合现场调试
uv run --group desktop python build.py --mode onedir --console --smoke-test
# 单文件、无控制台的交付版本
uv run --group desktop python build.py --mode onefile --smoke-test
```

产物位于 `backend/release/`。`backend/static`、`backend/build`、`backend/release` 均为生成
目录，不要手工维护；打包前先关闭正在运行的旧 EXE。

## 扩展 shadcn/vue 组件

新增 UI 组件通过 CLI 写入本地源码，并遵循 `.agents/skills/shadcn-vue` 中的规则：

```powershell
cd frontend
pnpm dlx shadcn-vue@latest add <component>
```

代码结构、设计原理与维护指南见 [docs/技术文档.md](docs/技术文档.md)。
