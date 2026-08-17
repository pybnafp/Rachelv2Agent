# Rachel-v2 Frontend

React 19 + Vite + TypeScript SPA for the Rachel-v2 retro-synthesis platform
(M2). Talks to the FastAPI backend (`../backend`, port 8000) through the
Vite dev proxy; auth token is stored via Zustand persist.

## Stack

- React 19 + react-router-dom 7（路由 + 登录守卫）
- Zustand（persist 认证状态）、TanStack Query（数据请求与轮询）
- Tailwind CSS 3、自建轻量 UI 基件（`src/components/ui/`）
- @xyflow/react（React Flow 12）路线树画布
- @rdkit/rdkit（WASM，本地打包：postinstall 拷贝到 `public/rdkit/`）
- Vitest + Testing Library（jsdom）

## 目录结构

```
src/
  api/          # API client（fetch 封装 + token 注入）
  components/   # Layout、MoleculeView、RouteTreeCanvas、NodeDrawer、StatusBadge、ui/
  pages/        # LoginPage / RegisterPage / SubmitPage / JobsPage / JobDetailPage
  stores/       # Zustand（auth）
  lib/          # 工具（树布局等）
  tests/        # Vitest 测试 + fixtures
  types.ts      # 与后端契约对齐的唯一类型源
```

## 脚本

```bash
npm install      # postinstall 自动拷贝 RDKit WASM 到 public/rdkit/
npm run dev      # http://localhost:5173（/api 代理到 :8000，后端先启动）
npm test         # Vitest（一次性：npm test -- --run）
npm run build    # tsc -b + vite build → dist/（index.html + assets + rdkit WASM）
npm run preview  # 本地预览 dist/
npm run lint     # oxlint
```

## 测试

54 个测试覆盖：路由守卫、认证页、提交页（RDKit mock）、任务列表/详情页、
路线树画布与布局算法、状态徽章、Layout 顶栏（登录/登出/admin）。运行：
`npm test -- --run`。

## 生产构建

`npm run build` 产出 `dist/` 静态文件（含 `dist/rdkit/RDKit_minimal.wasm`），
由 Nginx 托管（M5 部署阶段接入）。
