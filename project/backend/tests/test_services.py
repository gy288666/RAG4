"""服务层单元测试：切片、加密、解析、向量隔离、Rerank 降级。"""

from __future__ import annotations

import os

import pytest

from app.core.config import settings
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    hash_password,
    mask_secret,
    validate_email,
    validate_password,
    verify_password,
)
from app.modeling import ModelDescriptor, RankedIndex
from app.modeling import registry as model_registry
from app.services import chunking_service, embedding_service, parser_service, rerank_service
from app.services.config_service import RuntimeConfig
from app.services.parser_service import TextBlock
from app.services.vector_store import LocalVectorStore, RetrievedChunk, VectorRecord, collection_name


# ------------------------------------------------------------
# 密码与加密
# ------------------------------------------------------------


def test_bcrypt_roundtrip():
    hashed = hash_password("pwd123456")
    assert hashed != "pwd123456"          # 拒绝明文存储
    assert hashed.startswith("$2")        # bcrypt 标识
    assert verify_password("pwd123456", hashed)
    assert not verify_password("wrongpwd", hashed)


def test_bcrypt_handles_overlong_password():
    long_password = "很长的密码" * 40
    assert verify_password(long_password, hash_password(long_password))


def test_aes256_roundtrip_and_mask():
    plaintext = "sk-1234567890abcdefghij"
    ciphertext = encrypt_secret(plaintext)
    assert ciphertext != plaintext
    assert decrypt_secret(ciphertext) == plaintext
    # 相同明文两次加密结果不同（随机 nonce）
    assert encrypt_secret(plaintext) != ciphertext

    masked = mask_secret(plaintext)
    assert masked.startswith("sk-") and masked.endswith("ghij") and "****" in masked
    assert mask_secret("") == ""


def test_decrypt_tolerates_legacy_plaintext():
    """兼容加密上线前写入的历史明文配置。"""
    assert decrypt_secret("legacy-plain-key") == "legacy-plain-key"
    assert decrypt_secret("") == ""


@pytest.mark.parametrize(
    "email,expected",
    [
        ("a@outlook.com", True),
        ("b@qq.com", True),
        ("c@gmail.com", True),
        ("d@163.com", True),
        ("e@stu.edu.cn", True),
        ("no-at-sign", False),
        ("f@unknown-domain.io", False),
        ("", False),
    ],
)
def test_email_rules(email, expected):
    assert validate_email(email)[0] is expected


def test_password_rules():
    assert validate_password("123456")[0] is True
    assert validate_password("12345")[0] is False


# ------------------------------------------------------------
# 切片
# ------------------------------------------------------------


def test_chunking_respects_size_and_overlap():
    text = "这是一个测试句子。" * 200
    chunks = chunking_service.split_blocks([TextBlock(text=text)], chunk_size=200, overlap=20)

    assert len(chunks) > 1
    assert all(len(c.text) <= 200 + 20 for c in chunks)
    # chunk_index 全局连续且 0-based [S-3]
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunking_keeps_page_number():
    blocks = [TextBlock(text="第一页内容。" * 50, page=1), TextBlock(text="第二页内容。" * 50, page=2)]
    chunks = chunking_service.split_blocks(blocks, chunk_size=150, overlap=10)
    assert {c.page for c in chunks} == {1, 2}


def test_chunking_short_text_produces_single_chunk():
    chunks = chunking_service.split_blocks([TextBlock(text="很短的一句话。")], 600, 60)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0


def test_chunking_handles_text_without_punctuation():
    chunks = chunking_service.split_blocks([TextBlock(text="A" * 1000)], chunk_size=300, overlap=30)
    assert len(chunks) >= 3
    assert all(c.text for c in chunks)


# ------------------------------------------------------------
# 解析
# ------------------------------------------------------------


def test_parse_txt_with_gbk_encoding(tmp_path):
    path = tmp_path / "gbk.txt"
    path.write_bytes("中文编码自动识别测试内容。".encode("gbk"))
    result = parser_service.parse(str(path))
    assert "中文编码自动识别" in result.blocks[0].text


def test_parse_markdown_strips_syntax(tmp_path):
    path = tmp_path / "note.md"
    path.write_text(
        "# 一级标题\n\n这是**加粗**文本与[链接](https://example.com)。\n\n- 列表项\n",
        encoding="utf-8",
    )
    text = parser_service.parse(str(path)).blocks[0].text
    assert "一级标题" in text
    assert "加粗" in text and "**" not in text
    assert "链接" in text and "https://example.com" not in text


def test_parse_pdf_extracts_text_with_page_numbers(tmp_path):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "sample.pdf"
    document = fitz.open()
    for i in range(2):
        page = document.new_page()
        page.insert_text((72, 72), f"Page {i + 1}: Retrieval Augmented Generation overview text.")
    document.save(str(path))
    document.close()

    result = parser_service.parse(str(path))
    assert result.page_count == 2
    assert [b.page for b in result.blocks] == [1, 2]
    assert "Retrieval" in result.blocks[0].text


def test_parse_rejects_unsupported_format(tmp_path):
    path = tmp_path / "a.exe"
    path.write_bytes(b"MZ")
    with pytest.raises(parser_service.ParseError):
        parser_service.parse(str(path))


def test_parse_missing_file():
    with pytest.raises(parser_service.ParseError):
        parser_service.parse("/no/such/file.txt")


# ------------------------------------------------------------
# 向量库隔离 [PRD 4.2.1]
# ------------------------------------------------------------


def test_collection_naming_rule():
    assert collection_name(12) == "col_user_12"
    assert collection_name(12, "domain-embedding-v1") != collection_name(
        12, "domain-embedding-v2"
    )
    assert collection_name(12, "domain-embedding-v1").startswith("col_user_12__")


def test_vector_store_isolates_users(tmp_path):
    store = LocalVectorStore(str(tmp_path))
    store.add(
        1,
        [
            VectorRecord(
                id="doc_a:0", text="用户一的资料", embedding=[1.0, 0.0], doc_id="doc_a",
                user_id=1, file_name="a.txt", chunk_index=0,
            )
        ],
    )
    store.add(
        2,
        [
            VectorRecord(
                id="doc_b:0", text="用户二的资料", embedding=[1.0, 0.0], doc_id="doc_b",
                user_id=2, file_name="b.txt", chunk_index=0,
            )
        ],
    )

    # 用户 1 检索不到用户 2 的任何片段
    hits = store.search(1, [1.0, 0.0], top_n=10)
    assert len(hits) == 1
    assert hits[0].doc_id == "doc_a"
    assert store.count(1) == 1 and store.count(2) == 1

    # [S-3] 按 doc_id 精确删除
    store.delete_document(1, "doc_a")
    assert store.count(1) == 0
    assert store.count(2) == 1

    store.drop_user(2)
    assert store.count(2) == 0


def test_vector_store_isolates_embedding_versions(tmp_path):
    store = LocalVectorStore(str(tmp_path))
    first = VectorRecord(
        id="doc_a:0",
        text="第一版向量",
        embedding=[1.0, 0.0],
        doc_id="doc_a",
        user_id=1,
        file_name="a.txt",
        chunk_index=0,
        embedding_model_version="domain-v1",
    )
    second = VectorRecord(
        id="doc_a:0",
        text="第二版向量",
        embedding=[0.0, 1.0, 0.0],
        doc_id="doc_a",
        user_id=1,
        file_name="a.txt",
        chunk_index=0,
        embedding_model_version="domain-v2",
    )

    store.add(1, [first], index_version="domain-v1")
    store.add(1, [second], index_version="domain-v2")

    assert store.search(1, [1.0, 0.0], 5, index_version="domain-v1")[0].text == "第一版向量"
    assert store.search(1, [0.0, 1.0, 0.0], 5, index_version="domain-v2")[0].text == "第二版向量"
    assert store.count(1, index_version="domain-v1") == 1
    assert store.count(1, index_version="domain-v2") == 1

    # 未指定版本时按 doc_id 清理所有模型版本，避免删除文档后残留旧索引。
    store.delete_document(1, "doc_a")
    assert store.count(1, index_version="domain-v1") == 0
    assert store.count(1, index_version="domain-v2") == 0


def test_vector_record_metadata_contains_required_fields():
    record = VectorRecord(
        id="doc_x:3", text="内容", embedding=[0.1], doc_id="doc_x", user_id=7,
        file_name="paper.pdf", chunk_index=3, page=5,
    )
    meta = record.metadata()
    assert meta == {
        "doc_id": "doc_x",
        "user_id": 7,
        "file_name": "paper.pdf",
        "chunk_index": 3,
        "page": 5,
    }
    # 无页码时省略 page 键，避免向量库拒绝 None 值
    record.page = None
    assert "page" not in record.metadata()


# ------------------------------------------------------------
# Rerank 降级 [M-6]
# ------------------------------------------------------------


class _StubConfig:
    rerank_api_url = "https://invalid.example.com/rerank"
    rerank_api_key = "key"
    rerank_top_k = 2
    rerank_model = "BAAI/bge-reranker-v2-m3"


class _LocalConfig(_StubConfig):
    rerank_provider = "local"
    rerank_version = "domain-reranker-v1"
    rerank_local_path = "models/domain-reranker-v1"
    embedding_provider = "local"
    embedding_version = "domain-embedding-v1"
    embedding_local_path = "models/domain-embedding-v1"
    embedding_model = "unused"
    embedding_base_url = ""
    embedding_api_key = ""


def test_registry_resolves_local_model_adapters(monkeypatch):
    embedding = object()
    reranker = object()
    monkeypatch.setattr(model_registry, "_local_embedding", lambda path, version: embedding)
    monkeypatch.setattr(model_registry, "_local_reranker", lambda path, version: reranker)

    assert model_registry.resolve_embedding_model(_LocalConfig()) is embedding
    assert model_registry.resolve_reranker_model(_LocalConfig()) is reranker


def test_model_facades_delegate_to_adapters(monkeypatch):
    class StubEmbedding:
        descriptor = ModelDescriptor("embedding", "local", "stub", "v1", 2)

        def embed_documents(self, texts):
            return [[float(len(text)), 1.0] for text in texts]

        def embed_query(self, text):
            return [float(len(text)), 1.0]

    class StubReranker:
        descriptor = ModelDescriptor("reranker", "local", "stub", "v1")

        def rank(self, query, passages, top_k):
            return [RankedIndex(index=1, score=0.9), RankedIndex(index=0, score=0.2)][:top_k]

    monkeypatch.setattr(settings, "DEV_MOCK_AI", False)
    monkeypatch.setattr(model_registry, "resolve_embedding_model", lambda config: StubEmbedding())
    monkeypatch.setattr(model_registry, "resolve_reranker_model", lambda config: StubReranker())
    monkeypatch.setattr(embedding_service, "_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(rerank_service.usage_service, "record", lambda *args, **kwargs: None)

    assert embedding_service.embed_texts(["ab", "四个汉字"], _LocalConfig()) == [
        [2.0, 1.0],
        [4.0, 1.0],
    ]
    candidates = [
        RetrievedChunk(text="first", doc_id="d", file_name="f", chunk_index=0),
        RetrievedChunk(text="second", doc_id="d", file_name="f", chunk_index=1),
    ]
    ranked, warnings = rerank_service.rerank("query", candidates, _LocalConfig())
    assert [item.text for item in ranked] == ["second", "first"]
    assert warnings == []


def test_rerank_falls_back_on_failure(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MOCK_AI", False)
    monkeypatch.setattr(settings, "RERANK_TIMEOUT", 0.01)

    candidates = [
        RetrievedChunk(text=f"片段{i}", doc_id="d", file_name="f.txt", chunk_index=i)
        for i in range(5)
    ]
    result, warnings = rerank_service.rerank("问题", candidates, _StubConfig())

    # 不抛异常，降级为向量检索 Top-K，并携带告警
    assert len(result) == 2
    assert warnings == [rerank_service.WARNING_RERANK_TIMEOUT]


def test_rerank_skipped_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "DEV_MOCK_AI", False)

    class _NoKey(_StubConfig):
        rerank_api_key = ""

    candidates = [
        RetrievedChunk(text=f"片段{i}", doc_id="d", file_name="f.txt", chunk_index=i)
        for i in range(5)
    ]
    result, warnings = rerank_service.rerank("问题", candidates, _NoKey())
    assert len(result) == 2
    assert warnings == []


def test_rerank_parses_cohere_and_bailian_shapes():
    assert rerank_service._parse_results(
        {"results": [{"index": 2, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.4}]}
    ) == [(2, 0.9), (0, 0.4)]
    assert rerank_service._parse_results(
        {"output": {"results": [{"index": 1, "relevance_score": 0.7}]}}
    ) == [(1, 0.7)]
    assert rerank_service._parse_results({"unexpected": True}) == []


# ------------------------------------------------------------
# 上传目录隔离
# ------------------------------------------------------------


def test_upload_directory_is_per_user():
    from app.services.document_service import user_upload_dir

    path = user_upload_dir(42)
    assert path.endswith(os.path.join(settings.UPLOAD_DIR.rstrip("/"), "42").split(os.sep)[-1])
    assert os.path.isdir(path)


def test_runtime_config_clamps_overlap(client):
    """overlap 超过 chunk_size 时被强制收敛，防止切片死循环。"""
    from app.core.database import SessionLocal
    from app.services import config_service

    with SessionLocal() as db:
        config_service.set_value(db, config_service.CHUNK_SIZE, "200")
        config_service.set_value(db, config_service.CHUNK_OVERLAP, "500")
        runtime = RuntimeConfig(db)
        assert runtime.chunk_overlap < runtime.chunk_size
