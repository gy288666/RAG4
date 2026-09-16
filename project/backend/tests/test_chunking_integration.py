"""Parser compatibility and RAG4 upload -> vector metadata -> SSE contracts."""

import json

import pytest
from pydantic import ValidationError

from app.chunking import ChunkingEngine, FormulaMetadata, ParsedBlock, SourceInfo, TableMetadata
from app.chunking.adapter import adapt_parse_result
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document
from app.models.usage_log import UsageLog
from app.services import chunking_service, document_service, parser_service, vector_store
from app.services.parser_service import ParseResult, TextBlock


def upload(client, headers, name="paper.txt", text="自注意力机制是 Transformer 的核心。" * 30):
    body = client.post("/api/v1/docs/upload", headers=headers,
                       files=[("files", (name, text.encode("utf-8"), "text/plain"))]).json()
    assert body["code"] == 200, body
    doc_id = body["data"][0]["id"]
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        return doc_id, doc.user_id, doc.status


@pytest.fixture(params=["local", "chroma"])
def storage(request, tmp_path, monkeypatch):
    cls = vector_store.LocalVectorStore if request.param == "local" else vector_store.ChromaVectorStore
    store = cls(str(tmp_path / request.param))
    monkeypatch.setattr(vector_store, "_store", store)
    return store


def hits(store, user_id):
    from app.services.embedding_service import _mock_embedding

    return store.search(user_id, _mock_embedding("自注意力机制"), top_n=100)


def test_legacy_adapter_preserves_page_ocr_source_and_does_not_mutate_input():
    old = ParseResult([TextBlock("page two", 2)], True, 3)
    result = adapt_parse_result(old, document_id="doc1", file_name="paper.pdf")
    assert result.parser_version == "rag3-parser-v1"
    assert result.page_count == 3 and result.source.used_ocr
    assert result.blocks[0].page_start == result.blocks[0].page_end == 2
    assert old == ParseResult([TextBlock("page two", 2)], True, 3)
    assert ChunkingEngine().split(result).child_chunks[0].page_start == 2


def test_adapter_uses_structured_metadata_without_inventing_legacy_structure():
    table = TableMetadata(table_id="t", columns=("x",), rows=(("1",),))
    formula = FormulaMetadata(formula_id="f", latex="x=1")
    structured = (
        ParsedBlock(block_id="t", kind="table", text="x | 1", table=table),
        ParsedBlock(block_id="f", kind="formula", text="x=1", formula=formula),
    )
    old = ParseResult([TextBlock("flattened legacy text")], structured_blocks=structured, parser_version="structured-v1")
    parsed = adapt_parse_result(old, document_id="d", file_name="d.docx", source=SourceInfo(uri="upload:d"))
    chunks = ChunkingEngine().split(parsed)
    assert chunks.child_chunks[0].table_metadata == (table,)
    assert chunks.child_chunks[1].formula_metadata == (formula,)
    assert old.blocks[0].text == "flattened legacy text"
    assert adapt_parse_result(ParseResult([]), document_id="d", file_name="x.txt").blocks == ()


@pytest.mark.parametrize("result", [None, [], ParseResult([TextBlock(None)]), ParseResult([TextBlock("x", 0)])])
def test_invalid_legacy_inputs_rejected(result):
    with pytest.raises((TypeError, ValidationError)):
        adapt_parse_result(result, document_id="d", file_name="x.txt")


def test_markdown_opt_in_keeps_legacy_text_and_preserves_headings(tmp_path):
    path = tmp_path / "paper.md"
    path.write_text("# Paper\n\nBody **bold**.\n\n## Method\n\nText.\n\n```python\n# code, not heading\n```\n\nResults\n-------\nFinding.", encoding="utf-8")
    legacy = parser_service.parse(str(path))
    structured = parser_service.parse(str(path), structured=True)
    assert legacy.blocks == structured.blocks
    assert legacy.structured_blocks is None
    assert [b.text for b in structured.structured_blocks if b.kind == "heading"] == ["Paper", "Method", "Results"]
    assert next(b for b in structured.structured_blocks if b.kind == "code").text == "# code, not heading"
    parsed = adapt_parse_result(structured, document_id="d", file_name="paper.md")
    result = ChunkingEngine().split(parsed)
    assert {c.section_path for c in result.child_chunks} == {("Paper",), ("Paper", "Method"), ("Paper", "Results")}


def test_markdown_csharp_title_and_code_indentation_are_not_lost():
    from app.chunking.adapter import markdown_blocks

    blocks = markdown_blocks("# C#\n\n## Details ###\n\n```python\ndef f():\n    if True:\n        return 1\n```\n")
    assert [b.text for b in blocks[:2]] == ["C#", "Details"]
    assert blocks[2].text == "def f():\n    if True:\n        return 1"


def test_default_upload_remains_exact_rag3(client, user_headers, storage, monkeypatch):
    assert settings.DOCUMENT_CHUNKING_ENGINE == "rag3"
    original_add = storage.add
    captured = []

    def capture(user_id, records, **kwargs):
        captured.extend(records)
        original_add(user_id, records, **kwargs)

    monkeypatch.setattr(storage, "add", capture)
    text = "同一份基线文本。" * 200
    doc_id, user_id, status = upload(client, user_headers, text=text)
    assert status == "ready"
    expected = chunking_service.split_blocks([TextBlock(text)], chunk_size=600, overlap=60)
    assert [r.text for r in captured] == [c.text for c in expected]
    assert [r.id for r in captured] == [f"{doc_id}:{i}" for i in range(len(expected))]
    assert all("chunking_version" not in r.metadata() for r in captured)
    assert all("chunking" not in h.extra for h in hits(storage, user_id))


def test_rag4_upload_metadata_sse_and_switch_back(client, user_headers, storage, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_CHUNKING_ENGINE", "rag4")
    doc_id, user_id, status = upload(client, user_headers, "paper.md", "# Paper\n\n## Method\n\n" + "自注意力机制。" * 100)
    assert status == "ready"
    stored = hits(storage, user_id)
    assert stored and all(not h.extra["chunking"]["is_parent"] for h in stored)
    assert all(h.extra["chunking_version"] == settings.RAG4_CHUNKING_VERSION for h in stored)
    method = next(h.extra["chunking"] for h in stored if h.extra["chunking"]["title"] == "Method")
    assert method["section_path"] == ["Paper", "Method"]
    assert method["parent_chunk_id"].startswith("chunk_")
    assert method["tokenizer_id"] == "unicode-codepoint-v1"
    assert method["source_locator"]["spans"]
    session_id = client.post("/api/v1/chat/session", headers=user_headers).json()["data"]["session_id"]
    response = client.post("/api/v1/chat/query", headers=user_headers,
                           json={"session_id": session_id, "query": "自注意力机制是什么？", "enable_rag": True})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data:")]
    done = events[-1]
    assert done["citations"] and done["warnings"] == []
    assert {"index", "doc_name", "page", "chunk_index", "snippet"} <= done["citations"][0].keys()
    assert done["citations"][0]["doc_name"] == "paper.md"
    before = {h.chunk_index: h.extra for h in stored}
    monkeypatch.setattr(settings, "DOCUMENT_CHUNKING_ENGINE", "rag3")
    assert document_service.process_document(doc_id) == "ready"
    assert {h.chunk_index: h.extra for h in hits(storage, user_id)} == before
    new_id, _, status = upload(client, user_headers)
    assert status == "ready"
    assert all("chunking" not in h.extra for h in hits(storage, user_id) if h.doc_id == new_id)


def test_pdf_upload_preserves_page_and_metadata(client, user_headers, storage, monkeypatch):
    import fitz

    monkeypatch.setattr(settings, "DOCUMENT_CHUNKING_ENGINE", "rag4")
    pdf = fitz.open()
    for i in range(2):
        pdf.new_page().insert_text((72, 72), f"Page {i + 1}: Retrieval Augmented Generation overview text.")
    payload = pdf.tobytes()
    pdf.close()
    body = client.post("/api/v1/docs/upload", headers=user_headers,
                       files=[("files", ("paper.pdf", payload, "application/pdf"))]).json()
    with SessionLocal() as db:
        doc = db.get(Document, body["data"][0]["id"])
        assert doc.status == "ready"
        stored = hits(storage, doc.user_id)
    assert {s["page_start"] for h in stored for s in h.extra["chunking"]["source_locator"]["spans"]} == {1, 2}
    assert all(h.page == h.extra["chunking"]["page_start"] for h in stored)


def test_chunking_failure_keeps_existing_index_and_records_error(client, user_headers, storage, monkeypatch):
    _, user_id, status = upload(client, user_headers)
    assert status == "ready"
    before = hits(storage, user_id)
    monkeypatch.setattr(settings, "DOCUMENT_CHUNKING_ENGINE", "rag4")

    def fail(*args, **kwargs):
        raise RuntimeError("injected chunking failure")

    monkeypatch.setattr(document_service.ChunkingEngine, "split", fail)
    doc_id, _, status = upload(client, user_headers)
    assert status == "failed"
    assert hits(storage, user_id) == before
    with SessionLocal() as db:
        log = db.query(UsageLog).filter_by(ref_id=doc_id, event_type="document_chunking").one()
        assert not log.is_success and log.duration_ms >= 0
        assert "injected chunking failure" in log.error_message


def test_embedding_count_mismatch_never_writes(client, user_headers, storage, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_CHUNKING_ENGINE", "rag4")
    monkeypatch.setattr(document_service.embedding_service, "embed_texts", lambda *a, **kw: [])
    doc_id, user_id, status = upload(client, user_headers)
    assert status == "failed" and storage.count(user_id) == 0
    with SessionLocal() as db:
        log = db.query(UsageLog).filter_by(ref_id=doc_id, event_type="document_process").one()
        assert "数量" in log.error_message
