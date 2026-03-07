# Paper SOP Backend

自动化研究论文 SOP 系统 API（v4.0），前后端分离部署时的后端服务。

## 本地开发

```bash
pyenv local 3.12.9
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

创建 `.env`（不提交），至少设置：

- `SECRET_KEY`、`OPENAI_API_KEY`、`GEMINI_API_KEY`
- 可选：`CORS_ORIGINS=http://localhost:5173`（前端开发地址）

不设置 `DATABASE_URL` 时使用 SQLite（`./data/users.db`）。首次可执行：

```bash
python scripts/init_db.py
python scripts/create_admin.py
```

启动：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API 文档：<http://localhost:8000/docs>
- 导出 OpenAPI：`python scripts/export_openapi.py` → `docs/openapi.json`

## 提交前自动校验（推荐）

项目已内置 `pre-commit` 配置，会在提交前自动执行 API 文档一致性检查：

```bash
pip install pre-commit
pre-commit install
```

手动运行所有钩子：

```bash
pre-commit run --all-files
```

## 部署

- 由运维通过 Traefik/Nginx 等反向代理暴露 API（**不在此仓库内配置 Nginx/ngrok**）。
- 使用 Docker 时：构建 `Dockerfile`，通过环境变量注入所有配置；挂载 `VECTOR_DB_PATH`、`PROJECTS_PATH` 对应 volume（如 `/app/data/chroma`、`/app/data/files`）。
- PostgreSQL：运维执行 `docs/postgresql_schema.sql` 建表，并设置 `DATABASE_URL`。
- 环境变量说明见 [ENV.md](ENV.md)，数据库说明见 [docs/DATABASE.md](docs/DATABASE.md)，接口文档与矩阵见 [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md)。
