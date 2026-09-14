"""知识库管理模块 ``/api/v1/docs``（api_document 第 3 章）。"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import BadRequest, NotFound, success
from app.models.document import ALL_STATUSES, STATUS_LABELS, Document
from app.models.user import User
from app.services import document_service
from app.utils.datetime_utils import fmt

router = APIRouter(prefix="/docs", tags=["知识库"])


def _serialize(document: Document) -> dict:
    return {
        "id": document.id,
        "file_name": document.file_name,
        "file_size": document.file_size,
        "status": document.status,
        "status_label": STATUS_LABELS.get(document.status, document.status),
        "created_at": fmt(document.created_at),
        "updated_at": fmt(document.updated_at),  # [M-1] 前端据此判断是否卡滞
    }


@router.post("/upload", summary="上传多文档")
async def upload(
    files: list[UploadFile] = File(..., description="最多 10 个文件，单文件最大 50MB"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not files:
        raise BadRequest("请至少选择一个文件")
    if len(files) > settings.MAX_FILES_PER_UPLOAD:
        raise BadRequest(f"单次最多上传 {settings.MAX_FILES_PER_UPLOAD} 个文件")

    allowed = settings.allowed_extension_set
    created: list[Document] = []

    for upload_file in files:
        file_name = os.path.basename(upload_file.filename or "").strip()
        if not file_name:
            raise BadRequest("存在文件名为空的文件")

        ext = os.path.splitext(file_name)[1].lower()
        if ext not in allowed:
            raise BadRequest(
                f"文件「{file_name}」格式不支持，仅支持 {'、'.join(sorted(allowed))}"
            )

        content = await upload_file.read()
        if not content:
            raise BadRequest(f"文件「{file_name}」内容为空")
        if len(content) > settings.MAX_FILE_SIZE:
            limit_mb = settings.MAX_FILE_SIZE // (1024 * 1024)
            raise BadRequest(f"文件「{file_name}」超过 {limit_mb}MB 上限")

        doc_id = document_service.new_document_id()
        local_path = document_service.save_uploaded_file(user.id, doc_id, file_name, content)
        created.append(
            document_service.create_document(
                db,
                user_id=user.id,
                doc_id=doc_id,
                file_name=file_name,
                file_size=len(content),
                local_path=local_path,
            )
        )

    # 元数据全部落库后再启动异步解析，避免后台线程读不到记录
    for document in created:
        document_service.enqueue(document.id)

    return success(
        [_serialize(d) for d in created], message="文档上传成功，后端已启动异步解析入库"
    )


@router.get("/list", summary="获取文档列表（支持轮询状态）")
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: str | None = Query(None, description="按解析状态过滤"),
    keyword: str | None = Query(None, description="按文件名模糊搜索"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if status and status not in ALL_STATUSES:
        raise BadRequest(f"非法的状态值：{status}")

    # 水平越权防御：始终以当前用户 user_id 过滤（PRD 5.2）
    conditions = [Document.user_id == user.id]
    if status:
        conditions.append(Document.status == status)
    if keyword:
        conditions.append(Document.file_name.like(f"%{keyword.strip()}%"))

    total = db.execute(select(func.count(Document.id)).where(*conditions)).scalar_one()
    items = (
        db.execute(
            select(Document)
            .where(*conditions)
            # id 为时间有序 ID，作为同秒记录的稳定次级排序键
            .order_by(Document.created_at.desc(), Document.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    return success(
        {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_serialize(d) for d in items],
        },
        message="获取成功",
    )


@router.post("/{doc_id}/retry", summary="重新处理失败文档")
def retry_document(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = db.get(Document, doc_id)
    if document is None or document.user_id != user.id:
        raise NotFound("文档不存在或无权访问")
    if document.status != "failed":
        raise BadRequest("仅失败状态的文档可以重新处理")

    document.status = "pending"
    db.add(document)
    db.commit()
    db.refresh(document)
    document_service.enqueue(document.id)
    return success(_serialize(document), message="已重新提交解析任务")


@router.delete("/{doc_id}", summary="删除文档")
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = db.get(Document, doc_id)
    # 不区分「不存在」与「不属于本人」，避免文档 ID 被探测
    if document is None or document.user_id != user.id:
        raise NotFound("文档不存在或无权访问")

    document_service.delete_document(db, document)
    return success(None, message="文档删除成功，已清理关联的向量与元数据")
