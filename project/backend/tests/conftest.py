"""pytest 公共夹具：使用 SQLite 内存库 + Mock AI，保证测试完全离线可跑。"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# 必须在导入 app 之前设置环境变量
_TMP_ROOT = tempfile.mkdtemp(prefix="rag_test_")
os.environ["ENV_FILE"] = str(Path(_TMP_ROOT) / "nonexistent.env")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_ROOT}/test.db"
os.environ["UPLOAD_DIR"] = f"{_TMP_ROOT}/uploads"
os.environ["CHROMA_DIR"] = f"{_TMP_ROOT}/chroma"
os.environ["DEV_MOCK_AI"] = "true"
os.environ["DOCUMENT_CHUNKING_ENGINE"] = "rag3"
os.environ["RAG4_CHUNKING_VERSION"] = "rag4-structured-v1"
os.environ["RAG4_CHILD_MAX_TOKENS"] = "256"
os.environ["RAG4_PARENT_MAX_TOKENS"] = "1024"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["RESET_REQUEST_INTERVAL_MINUTES"] = "10"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import ROLE_ADMIN, User  # noqa: E402
from app.services import config_service, document_service  # noqa: E402
from app.services import vector_store  # noqa: E402
from app.modeling.registry import clear_model_cache  # noqa: E402

# 测试中同步执行文档解析，便于直接断言最终状态
document_service.SYNCHRONOUS_PROCESSING = True


@pytest.fixture(scope="session", autouse=True)
def _prepare_database():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_state():
    """每个用例前清空业务数据与向量库，保证互不干扰。"""
    from app.models.chat import ChatMessage, ChatSession
    from app.models.document import Document
    from app.models.reset_request import PasswordResetRequest
    from app.models.system_config import SystemConfig
    from app.models.usage_log import UsageLog

    with SessionLocal() as db:
        for model in (
            ChatMessage,
            ChatSession,
            Document,
            PasswordResetRequest,
            UsageLog,
            SystemConfig,
            User,
        ):
            db.query(model).delete()
        db.commit()
    config_service.invalidate_cache()
    clear_model_cache()
    # 每个用例使用独立的向量库目录：chromadb 内部会按 path 缓存 system 实例，
    # 直接删除目录会让后续请求命中已失效的连接。
    settings.CHROMA_DIR = os.path.join(_TMP_ROOT, f"chroma_{uuid.uuid4().hex}")
    vector_store.reset_vector_store()
    yield


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


# ------------------------------------------------------------
# 账号夹具
# ------------------------------------------------------------

USER_EMAIL = "student@outlook.com"
USER_PASSWORD = "pwd123456"
ADMIN_EMAIL = "root@outlook.com"
ADMIN_PASSWORD = "admin123456"


def _register_and_login(client: TestClient, email: str, password: str) -> dict:
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    body = response.json()
    assert body["code"] == 200, body
    return body["data"]


@pytest.fixture
def user_token(client: TestClient) -> str:
    return _register_and_login(client, USER_EMAIL, USER_PASSWORD)["access_token"]


@pytest.fixture
def user_headers(user_token: str) -> dict:
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(client: TestClient) -> dict:
    with SessionLocal() as db:
        admin = User(
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD),
            role=ROLE_ADMIN,
            status=1,
        )
        db.add(admin)
        db.commit()
    response = client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}
