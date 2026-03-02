# 数据库说明

- **用途**：用户、鉴权、计费相关数据（PostgreSQL）；业务数据（项目、文档等）存文件系统（JSON/Markdown），见部署方案中的 volume 挂载。
- **生产**：使用 PostgreSQL，通过环境变量 `DATABASE_URL` 连接，例如：
  `postgresql://user:password@host:5432/dbname`
- **建表**：首次部署时由运维执行 `docs/postgresql_schema.sql`（或使用 Alembic 等迁移工具）。应用启动时会执行 `create_all`，若表已存在则不会重复创建。
- **本地开发**：不设置 `DATABASE_URL` 时使用 SQLite（`./data/users.db`），无需单独建表。
