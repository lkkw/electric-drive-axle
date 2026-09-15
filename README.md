# FastAPI + Vue 3 Full-stack Starter

一套已完成依赖锁定、类型检查和接口测试的前后端分离模板。后端提供 RESTful API 与
SSE 实时推送；前端使用 Vue 3、TypeScript、Pinia、Alova、Tailwind CSS v4、
shadcn/vue 和 Apache ECharts。

## 目录结构

```text
electric-drive-axle/
├─ backend/
│  ├─ app/
│  │  ├─ core/
│  │  │  └─ config.py             # 环境变量和应用配置
│  │  ├─ routers/
│  │  │  ├─ demo.py               # REST API 示例
│  │  │  └─ sse.py                # SSE StreamingResponse 示例
│  │  ├─ schemas/
│  │  │  ├─ demo.py               # REST 请求/响应模型
│  │  │  └─ sse.py                # SSE 消息模型
│  │  ├─ services/
│  │  │  ├─ demo_service.py       # REST 业务服务
│  │  │  └─ sse_service.py        # SSE 消息与编码服务
│  │  └─ main.py                  # FastAPI 工厂、CORS、路由挂载
│  ├─ tests/                       # REST、SSE 自动化测试
│  ├─ main.py                      # uv run main.py 本地开发启动器
│  ├─ desktop.py                   # Uvicorn + PyWebView 桌面入口
│  ├─ build.py                     # Vue 构建与 PyInstaller 打包流水线
│  ├─ pyproject.toml               # uv / Hatchling / Python 依赖配置
│  └─ uv.lock                      # 可复现的 Python 依赖锁
├─ frontend/
│  ├─ src/
│  │  ├─ api/demo.ts               # Alova API 方法
│  │  ├─ components/
│  │  │  ├─ charts/                # ECharts 按需注册与通用实时曲线
│  │  │  ├─ layout/                # 应用布局：AppLayout / AppSidebar / SiteHeader / nav
│  │  │  └─ ui/                    # shadcn/vue CLI 生成的组件源码
│  │  ├─ composables/              # 有界实时数据缓存及其单元测试
│  │  ├─ lib/utils.ts              # shadcn/vue 的 cn 工具
│  │  ├─ router/index.ts           # vue-router：在 children 中注册新页面
│  │  ├─ stores/useDemoStore.ts    # Pinia Setup Store
│  │  ├─ types/chart.ts            # 与业务协议解耦的图表类型
│  │  ├─ utils/alova.ts            # Alova 实例与拦截器
│  │  ├─ views/                    # 页面：DashboardView / SseDemo，新增页面放这里
│  │  ├─ App.vue
│  │  ├─ main.ts
│  │  └─ style.css                 # Tailwind v4 与语义主题变量
│  ├─ components.json              # shadcn/vue 配置
│  ├─ package.json
│  ├─ pnpm-lock.yaml
│  ├─ pnpm-workspace.yaml
│  └─ vite.config.ts               # alias、Tailwind 插件与 API 代理
└─ README.md
```

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js `^20.19.0 || >=22.12.0`（推荐当前 LTS）
- pnpm 11+

## 启动后端

打开第一个 PowerShell：

```powershell
cd backend
uv sync
uv run main.py
```

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>
- REST 示例：<http://127.0.0.1:8000/api/v1/demo>
- SSE 示例：<http://127.0.0.1:8000/api/v1/sse/events>

根目录 `main.py` 是便捷的本地开发启动器；真正的 ASGI 应用仍位于
`app/main.py`，这样既能使用熟悉的 `uv run main.py`，又能让 Hatchling 正确构建并
安装整个 `app` 包。生产环境仍可使用：

```powershell
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 启动前端

打开第二个 PowerShell：

```powershell
cd frontend
pnpm install
pnpm dev
```

浏览器访问 <http://127.0.0.1:5173>。Vite 会把 `/api` 代理到
`http://127.0.0.1:8000`，所以本地开发无需额外处理 CORS。

如果前后端部署在不同域名，复制 `frontend/.env.example` 为 `.env.local`，并将
`VITE_API_BASE_URL` 设置为后端的完整 API 地址，例如：

```dotenv
VITE_API_BASE_URL=https://api.example.com/api/v1
```

同时通过后端环境变量显式声明允许的前端来源：

```powershell
$env:CORS_ORIGINS="https://app.example.com"
uv run uvicorn app.main:app
```

## 前端布局

应用已使用 shadcn/vue 官方 Sidebar 组件搭好布局框架
（对应官方 blocks 的 dashboard-01 / sidebar-07）：

- `src/components/layout/AppLayout.vue`：布局壳（侧边栏 + 顶部栏 + 内容区）
- `src/components/layout/AppSidebar.vue`：侧边栏菜单配置（导航数据集中在此）
- `src/components/layout/SiteHeader.vue`：顶部栏（折叠按钮 + 面包屑）
- `src/components/demo/RouteTestPanel.vue`：路由测试面板（示例页面共用）

**现有页面**：仪表盘 `/`、SSE 实时消息 `/realtime`、示例页面一 `/pages/one`、
示例页面二 `/pages/two`（后两个为路由跳转测试界面，可直接替换为业务页面）。

**以后新增页面只需三步**：

1. 在 `src/views/` 下新建页面组件；
2. 在 `src/router/index.ts` 的 `children` 中注册路由；
3. 在 `src/components/layout/AppSidebar.vue` 的 `navMain` / `projects` 中追加菜单项
   （激活状态会跟随当前路由自动高亮）。

侧边栏支持折叠为图标模式（`Ctrl+B` 快捷键）与移动端抽屉，菜单带子菜单的
分组使用 `Collapsible` 折叠交互。

## 常用检查命令

后端：

```powershell
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

前端：

```powershell
cd frontend
pnpm type-check
pnpm test
pnpm build
```

## 扩展 shadcn/vue 组件

项目已执行过初始化，新增组件时继续通过 CLI 写入本地源码：

```powershell
cd frontend
pnpm dlx shadcn-vue@latest add dialog input table
```

## 实时曲线

模板使用 `echarts` 与 `vue-echarts`，并在
`src/components/charts/RealtimeLineChart.vue` 中提供通用时间序列组件。ECharts 采用
Canvas 渲染和按需注册，曲线组件又通过异步导入拆分为独立构建块，不阻塞主界面首屏。

SSE 页面中的数据链如下：

```text
SSE 原始消息 → 运行时字段校验 → 固定长度环形缓存 → 每 100 ms 批量发布 → ECharts setOption
```

示例最多保留 1000 个曲线点；SSE 断线重连时插入空值断点，避免把两个独立连接的
数据误连成一条连续曲线。真实设备项目应将明确的数值字段映射到通用类型：

```ts
interface RealtimeLinePoint {
  timestamp: number
  value: number | null
}
```

不要从显示文本中解析数值，也不要在每条 SSE 消息到达时直接重绘。新增散点图、热力图
或仪表盘时，在 `src/components/charts/echarts.ts` 中按需注册对应模块即可。

## 打包 Windows 桌面 EXE

桌面打包是可选交付层，不影响日常使用的 `uv run main.py`。`build.py` 会依次构建
Vue、把 `frontend/dist` 复制到生成目录 `backend/static`，再以 `desktop.py` 为入口调用
PyInstaller。桌面入口使用系统分配的随机端口，并由同一个 FastAPI 进程提供 API、SSE
和 Vue 页面。

首次准备桌面依赖：

```powershell
cd backend
uv sync --group desktop
```

建议先构建目录模式并保留控制台，便于检查启动日志：

```powershell
uv run --group desktop python build.py --mode onedir --console --smoke-test
```

生成文件位于：

```text
backend/release/Electric-Drive-Axle/Electric-Drive-Axle.exe
```

测试完成后再生成最终的单文件、无控制台版本：

```powershell
uv run --group desktop python build.py --mode onefile --smoke-test
```

最终文件位于 `backend/release/Electric-Drive-Axle.exe`。如需指定名称或图标：

```powershell
uv run --group desktop python build.py --mode onefile `
  --name "我的上位机" `
  --icon .\assets\app.ico
```

只想构建前端并本地测试桌面窗口，不执行 PyInstaller：

```powershell
uv run python build.py --prepare-only
uv run --group desktop python desktop.py
```

注意：

- `backend/static`、`backend/build` 和 `backend/release` 都是生成目录，不应手工维护。
- 最终打包前先关闭正在运行的旧 EXE，避免 Windows 占用输出文件。
- 用户可修改的配置、数据库和日志不要写进单文件 EXE 的内置资源目录；应保存到
  AppData 或 EXE 外部目录。
- 硬件项目的 DLL 使用 PyInstaller `--add-binary` 单独配置，CAN 驱动、业务配置和图标
  不属于通用模板，按具体项目补充。
- 目标电脑需要可用的 Microsoft Edge WebView2 Runtime 才能显示 PyWebView 窗口。

## SSE 注意事项

- `EventSource` 会自动重连；页面中不额外创建重连计时器，避免重复连接。
- 组件卸载和手动断开时都会执行 `close()`。
- 原生 `EventSource` 不能自定义 `Authorization` Header。需要 Bearer Token 或 POST
  SSE 时，可改用 Alova 的 `useSSE`，或采用同站 Cookie / 短期查询令牌方案。
- 生产环境使用 Nginx 等反向代理时，应关闭该 SSE 路径的响应缓冲。
