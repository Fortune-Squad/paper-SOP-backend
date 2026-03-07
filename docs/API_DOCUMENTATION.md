# Paper SOP Automation API 文档

> 单一 API 文档入口（已合并原 `API_OVERVIEW.md`）。  
> 本文档与代码自动校验，避免接口文档漂移。

## 1. 文档目标与使用方式

- 本文档分两部分：
  - **人工说明区**：解释每个模块做什么、关键接口怎么用。
  - **自动路由矩阵**：由脚本从代码生成，保证接口列表不漂移。
- 常用命令：
  - 校验：`python scripts/check_api_docs.py`
  - 刷新路由矩阵：`python scripts/check_api_docs.py --write`

## 2. 基础信息

- OpenAPI：运行服务后访问 `/docs`（Swagger）或 `/redoc`。
- 认证：除登录/注册/健康检查外，默认需 `Authorization: Bearer <access_token>`。
- 错误格式：统一 `{"detail": "..."}`（也可能是 `detail` 数组）。

## 3. 权限约定

- **公开**：无需登录。
- **登录**：需要有效 JWT。
- **管理员**：需要管理员角色（admin）。

## 4. 模块说明（已合并 API_OVERVIEW）

### 4.1 系统与健康检查

- `GET /`：服务基础信息。
- `GET /health`、`GET /api/health`：健康检查。
- `GET /api/version`：版本与能力说明（含 `compliance_redlines`）。
- `GET /api/test-mode`：查看测试模式（需登录）。
- `POST /api/test-mode`：切换测试模式（仅管理员）。

### 4.2 认证模块（`/api/auth/*`）

- `POST /api/auth/register`：注册（通常为待激活状态）。
- `POST /api/auth/login`：登录获取 `access_token`/`refresh_token`。
- `POST /api/auth/refresh`：刷新访问令牌。
- `POST /api/auth/logout`：退出登录。
- `GET /api/auth/me`：查询当前用户。
- `POST /api/auth/forgot-password`、`POST /api/auth/reset-password`：密码找回与重置。

### 4.3 用户与审计（管理员）

- 用户管理：`/api/users*`
  - 列表、详情、更新、激活/停用、删除、统计。
- 活动日志：`/api/activity-logs*`
  - 查询审计日志、统计、登录尝试记录。

### 4.4 项目主流程（`/api/projects*`）

- 项目基础：创建、列表、详情、状态、配置、删除。
- Bootloader：`skip`、`regenerate`、`outputs`、`confirm`。
- 步骤执行：`/steps/{step_id}/execute`、`/steps/{step_id}/reset`。
- Gate 管理：`check`、`approve`、`rollback`。
- 文档读取：`/documents`、`/documents/{doc_type}`。

### 4.5 执行与交付（v7 核心）

- 执行引擎：`/api/projects/{project_id}/execution/*`
  - 状态、WP 列表/详情、执行、冻结、子任务结果、预检、DAG。
- 交付流水线：`/api/projects/{project_id}/delivery/*`
  - 交付清单、交付状态、打包。

### 4.6 研究过程辅助模块

- Readiness Assessment：`/api/projects/{project_id}/ra/*`
  - request/result/override/status。
- Memory：`/api/projects/{project_id}/memory*`
  - 获取 memory、写入 learn/facts、删除 learn。
- Session Logs：`/api/projects/{project_id}/sessions*`
  - 创建会话、记录决策、写 wrap-up、查询会话。
- HIL：`/api/projects/{project_id}/hil/*` 与 `/api/hil/*`
  - 工单创建、查询、回答、取消、过期处理、阻塞/待处理查询。

### 4.7 实时接口

- `WS /ws/projects/{project_id}`：项目级实时推送。
- `WS /ws/global`：全局频道。

## 5. 路由矩阵（自动生成）

> 下方区块由脚本维护，请勿手改。

<!-- ROUTE_MATRIX_START -->
| 方法 | 路径 |
|---|---|
| DELETE | `/api/projects/{project_id}` |
| DELETE | `/api/projects/{project_id}/memory/learn/{index}` |
| DELETE | `/api/users/{user_id}` |
| GET | `/` |
| GET | `/api/activity-logs` |
| GET | `/api/activity-logs/login-attempts` |
| GET | `/api/activity-logs/stats` |
| GET | `/api/auth/me` |
| GET | `/api/health` |
| GET | `/api/hil/tickets/{ticket_id}` |
| GET | `/api/projects` |
| GET | `/api/projects/{project_id}` |
| GET | `/api/projects/{project_id}/delivery/manifest` |
| GET | `/api/projects/{project_id}/delivery/status` |
| GET | `/api/projects/{project_id}/documents` |
| GET | `/api/projects/{project_id}/documents/{doc_type}` |
| GET | `/api/projects/{project_id}/execution/dag` |
| GET | `/api/projects/{project_id}/execution/state` |
| GET | `/api/projects/{project_id}/execution/wps` |
| GET | `/api/projects/{project_id}/execution/wps/{wp_id}` |
| GET | `/api/projects/{project_id}/execution/wps/{wp_id}/subtasks` |
| GET | `/api/projects/{project_id}/execution/wps/{wp_id}/subtasks/{subtask_id}/preflight` |
| GET | `/api/projects/{project_id}/execution/wps/{wp_id}/subtasks/{subtask_id}/result` |
| GET | `/api/projects/{project_id}/hil/blocking` |
| GET | `/api/projects/{project_id}/hil/pending` |
| GET | `/api/projects/{project_id}/hil/tickets` |
| GET | `/api/projects/{project_id}/memory` |
| GET | `/api/projects/{project_id}/ra/status` |
| GET | `/api/projects/{project_id}/sessions` |
| GET | `/api/projects/{project_id}/sessions/{session_id}` |
| GET | `/api/projects/{project_id}/status` |
| GET | `/api/test-mode` |
| GET | `/api/users` |
| GET | `/api/users/stats` |
| GET | `/api/users/{user_id}` |
| GET | `/api/version` |
| GET | `/health` |
| POST | `/api/auth/forgot-password` |
| POST | `/api/auth/login` |
| POST | `/api/auth/logout` |
| POST | `/api/auth/refresh` |
| POST | `/api/auth/register` |
| POST | `/api/auth/reset-password` |
| POST | `/api/hil/process-expired` |
| POST | `/api/hil/tickets/{ticket_id}/answer` |
| POST | `/api/hil/tickets/{ticket_id}/cancel` |
| POST | `/api/projects` |
| POST | `/api/projects/analyze-clarity` |
| POST | `/api/projects/{project_id}/bootloader/confirm` |
| POST | `/api/projects/{project_id}/bootloader/regenerate` |
| POST | `/api/projects/{project_id}/bootloader/skip` |
| POST | `/api/projects/{project_id}/delivery/package` |
| POST | `/api/projects/{project_id}/execution/wps/{wp_id}/execute` |
| POST | `/api/projects/{project_id}/execution/wps/{wp_id}/freeze` |
| POST | `/api/projects/{project_id}/gates/{gate_name}/approve` |
| POST | `/api/projects/{project_id}/gates/{gate_name}/check` |
| POST | `/api/projects/{project_id}/hil/tickets` |
| POST | `/api/projects/{project_id}/loops/{gate_name}/rollback` |
| POST | `/api/projects/{project_id}/memory/facts` |
| POST | `/api/projects/{project_id}/memory/learn` |
| POST | `/api/projects/{project_id}/ra/{wp_id}/override` |
| POST | `/api/projects/{project_id}/ra/{wp_id}/request` |
| POST | `/api/projects/{project_id}/ra/{wp_id}/result` |
| POST | `/api/projects/{project_id}/sessions` |
| POST | `/api/projects/{project_id}/sessions/{session_id}/decisions` |
| POST | `/api/projects/{project_id}/sessions/{session_id}/wrapup` |
| POST | `/api/projects/{project_id}/steps/{step_id}/execute` |
| POST | `/api/projects/{project_id}/steps/{step_id}/reset` |
| POST | `/api/test-mode` |
| POST | `/api/users/{user_id}/activate` |
| POST | `/api/users/{user_id}/deactivate` |
| PUT | `/api/projects/{project_id}/bootloader/outputs` |
| PUT | `/api/projects/{project_id}/config` |
| PUT | `/api/projects/{project_id}/resource-card-input` |
| PUT | `/api/users/{user_id}` |
| WS | `/ws/global` |
| WS | `/ws/projects/{project_id}` |
<!-- ROUTE_MATRIX_END -->

