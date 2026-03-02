# 环境变量说明

所有配置通过环境变量注入，**不要将 `.env` 或密钥提交到仓库**。本地开发可在项目根目录创建 `.env` 文件（已加入 .gitignore）。

## 必填（生产必须设置）

| 变量 | 说明 |
|------|------|
| `SECRET_KEY` | JWT 签名密钥，生产环境必须设置强随机字符串 |
| `OPENAI_API_KEY` | OpenAI API Key |
| `GEMINI_API_KEY` | Google Gemini API Key |

## 数据库

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | 生产：`postgresql://user:pass@host:5432/dbname`；不设则使用 SQLite（仅开发） |

## 数据目录（部署时对应 volume 挂载）

| 变量 | 默认 | 说明 |
|------|------|------|
| `VECTOR_DB_PATH` | `./data/chroma` | ChromaDB 数据目录 |
| `PROJECTS_PATH` | `./data/files` | 业务文件（JSON/MD）目录 |

## CORS（前后端不同域时必配）

| 变量 | 说明 |
|------|------|
| `CORS_ORIGINS` | 允许的前端来源，逗号分隔，如 `https://app.example.com,https://www.example.com` |

## 可选

| 变量 | 默认 | 说明 |
|------|------|------|
| `APP_ENV` | `development` | `development` \| `production` |
| `APP_HOST` | `0.0.0.0` | 监听地址 |
| `APP_PORT` | `8000` | 监听端口 |
| `OPENAI_API_BASE` | - | OpenAI 代理 Base URL |
| `GEMINI_API_BASE` | - | Gemini 代理 Base URL |
| `OPENAI_MODEL` | `gpt-4-turbo` | 模型名 |
| `GEMINI_MODEL` | `gemini-2.0-flash-exp` | 模型名 |
| `GEMINI_GEM_CONFIG_PATH` | - | Gemini Gem 配置文件路径（可选） |
| `WORKFLOWS_DIR` | `./workflows` | 工作流 YAML 目录 |

其他如 `LOG_LEVEL`、`LOG_FILE`、重试与超时等见 `app/config.py` 中 `Settings` 定义。
