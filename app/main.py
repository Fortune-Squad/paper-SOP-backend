"""
FastAPI 主应用
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.api.projects import router as projects_router
from app.api.websocket import router as websocket_router
from app.api.hil import router as hil_router
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.activity_logs import router as activity_logs_router
from app.config import APP_VERSION, API_VERSION, settings
from app.db.database import init_db

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="Paper SOP Automation API",
    description="自动化研究论文 SOP 系统 API (v4.0) - 支持用户认证",
    version=APP_VERSION
)

# 配置 CORS（前后端不同域时由 CORS_ORIGINS 环境变量指定前端域名）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 应用启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    logger.info("Initializing database...")
    try:
        init_db()
        logger.info("[OK] Database initialized successfully")
    except Exception as e:
        logger.error(f"[ERROR] Database initialization failed: {str(e)}")


# 注册路由
app.include_router(auth_router)  # 认证路由
app.include_router(users_router)  # 用户管理路由
app.include_router(activity_logs_router)  # 活动日志路由
app.include_router(projects_router)
app.include_router(websocket_router)
app.include_router(hil_router)


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Paper SOP Automation API",
        "version": APP_VERSION,
        "api_version": API_VERSION,
        "status": "running",
        "sop_version": "v4.0"
    }


@app.get("/api/version")
async def get_version():
    """获取 API 版本信息"""
    return {
        "app_version": APP_VERSION,
        "api_version": API_VERSION,
        "sop_version": "v4.0",
        "features": [
            "16 steps workflow",
            "6 gates (including Gate 1.25 and Gate 1.6)",
            "Agentic-first AI interaction",
            "Reference QA system",
            "Auto-execution engine"
        ]
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


@app.get("/api/health")
async def api_health_check():
    """API健康检查（用于前端连接测试）"""
    return {
        "status": "healthy",
        "service": "Paper SOP Automation API",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.app_host, port=settings.app_port)
