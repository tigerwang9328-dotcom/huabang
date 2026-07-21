# frontend — Vue3 前端

<!-- agentmap:generated:start -->
## 范围

Vue3 + Element Plus + Pinia + ECharts + Vue Router 前端单体。20 个业务视图目录,经 Nginx 静态部署,API 走 `/api/v1`。**不负责**:后端业务逻辑、DB/第三方集成。

## 关键文件

- `package.json` — `huabang-ai-frontend`,Vue 3.4 / Element Plus 2.4 / Pinia 2.1 / ECharts 5.4 / axios 1.6 / vue-router 4.2 / TypeScript 5.3 / Vite 5
- `vite.config.ts` — 别名 `@`→`src`,dev proxy `/api`→`localhost:8000`,build outDir `dist`
- `src/main.ts` — 入口:createApp + Pinia + Router + ElementPlus(zhCn)+ 全量图标注册
- `src/router/index.ts` — **路由总表**,公开品牌官网 `/` + 登录 `/login` + 内部中台 `/app/*`(requireAuth 守卫)
- `src/stores/auth.ts` — Pinia 鉴权 store(token/user/permissions)
- `src/api/request.ts` — axios 实例,统一前缀 `/api/v1` + 拦截器 + `cancelRouteRequests`
- `src/layouts/` — `MainLayout.vue`(主框架/菜单)、`AuthLayout.vue`、`PublicLayout.vue`、`BasicLayout.vue`

## 视图目录(src/views/)

| 目录 | 主要页面 |
| --- | --- |
| `public/` | 品牌官网:Home/BrandStory/CompanyIntro/Products/Stores/Space/Contact(免登录) |
| `dashboard/` | 经营总览 |
| `report/` | 经营日报 |
| `boss/` | 老板看板 |
| `diagnosis/` | AI 经营诊断(overview + :module) |
| `store/` | 门店分析 |
| `product/` | 商品:Index/ProductMaster/SizeWall/SkuArchive |
| `inventory/` | 库存:Index/InventoryBalance/Warehouses |
| `member/` | 会员 |
| `finance/` | 财务:Index/FinanceOverview/FinanceCenterModule/FormalLedger/HistoricalFinance/ExpenseAnalysis/Payments/Reimbursements |
| `hr/` | HR:HrOverview/Employees/Attendance/Leaves |
| `marketing/` | 投流优化 InvestmentOptimization |
| `task/` | 任务:Index/Detail |
| `warning/` | 预警 |
| `system/` | 系统:AdminDashboard/Users/Roles/ModulePermissions/FieldPermissions/DataPermissions/OperationLogs/RegisterAudit/Security/Sync/BaisonApi |
| `ai/` | AI 入口 |
| `baison/` | 百胜 Shops |
| `dingtalk/` | 钉钉 |

## API 层(src/api/)

按业务域分文件:`auth/dashboard/finance/financeCenter/kingdeeFinance/hr/inventory/member/product/store/sync/system/task/ai/audit/baison/dingtalk/lifeDataAnalysis/lifeDataAnalysis` + `request.ts`(axios 基座)+ `routeRequestLifecycle.ts`。

## 组件(src/components/)

- `ai/BossAiChat.vue` — 老板 AI 聊天
- `ai/BossAiFloatingAssistant.vue` — 浮动助手

## 本地状态与失败行为

- 鉴权失败:router 守卫跳 `/login`;axios 401 拦截清 store
- 路由切换:`cancelRouteRequests` 取消上个路由未完成请求
- 构建产物 chunk 哈希失效:旧 index.html 引用已删 chunk → 404(需 `Cache-Control: no-cache`)

## 公共输入/输出

- 入参:用户交互 → axios `/api/v1/*` 调用后端
- 出参:Element Plus 表格/表单/ECharts 图表渲染
- 鉴权:`Authorization: Bearer <jwt>`(auth store 管理)

## 模块不变量

1. 构建产物 `frontend/dist` 由 Nginx 提供;**index.html 必须 `Cache-Control: no-cache`**(防 chunk 失效 404)。
2. 所有 API 请求经 `src/api/request.ts`(axios),前缀 `/api/v1`;**不直连 8000 端口**。
3. 路由权限在 `router/index.ts` 守卫 + 后端 `require_permission` **双重校验**。
4. 公开品牌官网 `/` 与内部中台 `/app/*` 物理隔离(public meta 不要求 requireAuth)。
5. Element Plus 中文 locale(`zhCn`)全局注入。

## 焦点测试/构建命令

```bash
cd /srv/huabang-ai-center/frontend
npm run type-check     # vue-tsc --noEmit
npm run build          # vite build → dist/
```
<!-- agentmap:generated:end -->

## 手动备注

部署前端:`npm run build` 后产物在 `frontend/dist/`,Nginx 已指向。**改 index.html 缓存策略需同步 Nginx 配置**(`/etc/nginx/sites-enabled/huabang` 的 `location /` 块)。历史踩坑:7/15 部署新 dist 后旧缓存 index.html 引用已删 chunk 致 404,需 Ctrl+F5 或加强 no-cache。`layouts/` 与 `router/` 下有大量 `.bak*` 备份文件,勿误用。
