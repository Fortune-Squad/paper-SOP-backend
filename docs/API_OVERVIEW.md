# Paper SOP Backend - API 总览

- **OpenAPI 文档**：运行服务后访问 `/docs`（Swagger UI）或 `/redoc`，或使用 `scripts/export_openapi.py` 导出 JSON。
- **认证**：除登录/注册等公开接口外，请求头需带 `Authorization: Bearer <access_token>`。

## 模块与主要端点

| 模块 | 前缀 | 说明 |
|------|------|------|
| 认证 | `POST /api/auth/login`, `POST /api/auth/register`, `POST /api/auth/refresh` | 登录、注册、刷新 Token |
| 用户 | `GET/POST /api/users/`, `GET/PUT/DELETE /api/users/{id}` | 用户管理（需 admin） |
| 活动日志 | `GET /api/activity-logs/` | 审计日志（需 admin） |
| 项目 | `GET/POST /api/projects/`, `GET/PUT/DELETE /api/projects/{id}` | 项目 CRUD、状态、配置 |
| 步骤 | `POST /api/projects/{id}/steps/{step_id}/execute`, `POST .../reset` | 步骤执行与重置 |
| Gate | `POST /api/projects/{id}/gates/{gate_name}/check` | Gate 检查 |
| 文档 | `GET /api/projects/{id}/documents`, `GET .../documents/{type}` | 项目文档列表与内容 |
| HIL | `GET/POST /api/hil/...` | 人机在环相关 |
| WebSocket | `WS /ws/projects/{project_id}` | 项目实时状态推送 |
| **v7 新增** | | |
| 执行 | `GET/POST /api/projects/{id}/execution/...` | 执行控制、预检、快照 |
| 交付 | `GET/POST /api/projects/{id}/delivery/...` | 交付进度、打包 |
| Readiness | `GET/POST /api/projects/{id}/readiness/...` | 就绪评估 |
| Memory | `GET/POST /api/memory/...` | 记忆存储 |
| Session Logs | `GET /api/projects/{id}/session-logs/...` | 会话日志 |
| 测试模式 | `GET/POST /api/test-mode` | 跳过前置/gate（仅 admin） |

## 健康与版本

- `GET /health`、`GET /api/health`：健康检查
- `GET /api/version`：版本与能力说明（含 compliance_redlines）

## 错误响应

统一 JSON 格式，包含 `detail`（字符串或列表）。401 表示未认证或 Token 失效，需刷新或重新登录。
