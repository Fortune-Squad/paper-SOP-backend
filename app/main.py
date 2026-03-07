"""
FastAPI 主应用

合规红线 (Compliance Red Lines) — SOP v7 §12
  1. 不做学术不端/代写代交付 — 不交付可直接投稿的论文正文/作业答案
  2. 不绕过限额/不轮询多 Key — 扩量只走申请更高额度/企业合同
  3. 不把闭源模型输出作为可售训练集 — 闭源模型最多用于内部 QA/打分
"""
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.api.projects import router as projects_router
from app.api.websocket import router as websocket_router
from app.api.hil import router as hil_router
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.activity_logs import router as activity_logs_router
from app.api.execution import router as execution_router
from app.api.delivery import router as delivery_router
from app.api.readiness import router as readiness_router
from app.api.memory import router as memory_router
from app.api.session_logs import router as session_logs_router
from app.config import APP_VERSION, API_VERSION, settings
from app.db.database import init_db
from app.middleware.auth import get_current_active_user, require_admin
from app.db.models import User as DBUser

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
    version=APP_VERSION,
    redirect_slashes=False,
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
app.include_router(execution_router)
app.include_router(delivery_router)
app.include_router(websocket_router)
app.include_router(hil_router)
app.include_router(readiness_router)
app.include_router(memory_router)
app.include_router(session_logs_router)


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
        ],
        "compliance_redlines": [
            "不做学术不端/代写代交付 — 不交付可直接投稿的论文正文/作业答案",
            "不绕过限额/不轮询多 Key — 扩量只走申请更高额度/企业合同",
            "不把闭源模型输出作为可售训练集 — 闭源模型最多用于内部 QA/打分"
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


@app.get("/api/test-mode")
async def get_test_mode(current_user: DBUser = Depends(get_current_active_user)):
    """获取测试模式状态"""
    return {"test_mode": settings.test_mode}


@app.post("/api/test-mode")
async def set_test_mode(enabled: bool = True, current_user: DBUser = Depends(require_admin)):
    """切换测试模式：跳过所有前置条件和 gate 检查（仅管理员）"""
    settings.test_mode = enabled
    return {"test_mode": settings.test_mode, "message": "测试模式已开启，可任意执行步骤" if enabled else "测试模式已关闭，恢复正常流程检查"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.app_host, port=settings.app_port, proxy_headers=True, forwarded_allow_ips="*")
