# Paper SOP Backend - 仅应用与依赖，密钥通过环境变量注入
FROM python:3.12-slim

WORKDIR /app

# 系统依赖（如 git 用于 GitManager）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码与迁移 / 脚本
COPY app/ app/
COPY workflows/ workflows/
COPY sop/ sop/
COPY alembic.ini .
COPY alembic/ alembic/
COPY scripts/ scripts/

# 数据目录由 volume 挂载，不在此创建
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
