"""RAG4 contracts and deterministic splitting, with a frozen RAG3 regression."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from app.chunking import (
    CharacterTokenCounter,
    ChunkingConfig,
    ChunkingEngine,
    ChunkSet,
    FormulaMetadata,
    ParsedBlock,
    ParsedDocument,
    SourceInfo,
    SourceSpan,
    TableMetadata,
    TokenizerTokenCounter,
)
from app.services.chunking_service import split_blocks
from app.services.parser_service import TextBlock


def document(*blocks: ParsedBlock, **updates) -> ParsedDocument:
    values = {
        "document_id": "doc-paper",
        "file_name": "paper.pdf",
        "source": SourceInfo(uri="upload://doc-paper", media_type="application/pdf"),
        "parser_version": "test-parser-v1",
        "blocks": blocks,
    }
    values.update(updates)
    return ParsedDocument(**values)


def split(text: str, *, child: int = 20, parent: int = 80):
    return ChunkingEngine().split(
        document(ParsedBlock(block_id="b0", text=text)),
        ChunkingConfig(child_max_tokens=child, parent_max_tokens=parent),
    )


def compact(text: str) -> str:
    """Boundary whitespace may be trimmed; every content character is retained."""
    return re.sub(r"\s+", "", text)


def test_paragraph_boundaries_take_precedence_over_sentence_and_character_cuts():
    result = split("First paragraph.\n\nSecond paragraph.", child=22, parent=80)
    assert [c.text for c in result.child_chunks] == ["First paragraph.", "Second paragraph."]
    assert len(result.parent_chunks) == 1
    assert result.verify()


def test_sentence_boundaries_are_used_when_paragraph_is_too_long():
    result = split("第一句话。第二句话。第三句话。", child=8)
    assert [c.text for c in result.child_chunks] == ["第一句话。", "第二句话。", "第三句话。"]


@pytest.mark.parametrize("text", ["A" * 2401, "中" * 2401, "English 中文🚀。\n\n" * 120])
def test_long_text_preserves_content_and_respects_both_budgets(text):
    result = split(text, child=31, parent=103)
    assert len(result.parent_chunks) > 1
    assert compact("".join(c.text for c in result.child_chunks)) == compact(text)
    assert compact("".join(c.text for c in result.parent_chunks)) == compact(text)
    assert all(0 < c.token_count <= 31 for c in result.child_chunks)
    assert all(0 < c.token_count <= 103 for c in result.parent_chunks)
    assert result.verify()


def test_heading_hierarchy_and_sibling_sections_are_retained():
    result = ChunkingEngine().split(document(
        ParsedBlock(block_id="h1", text="Introduction", kind="heading", heading_level=1),
        ParsedBlock(block_id="b1", text="Main text."),
        ParsedBlock(block_id="h2", text="Prior work", kind="heading", heading_level=2),
        ParsedBlock(block_id="b2", text="Earlier research."),
        ParsedBlock(block_id="h3", text="Method", kind="heading", heading_level=2),
        ParsedBlock(block_id="b3", text="New research."),
        ParsedBlock(block_id="h4", text="Results", kind="heading", heading_level=1),
        ParsedBlock(block_id="b4", text="Findings."),
    ))
    assert [c.section_path for c in result.parent_chunks] == [
        ("Introduction",), ("Introduction", "Prior work"),
        ("Introduction", "Method"), ("Results",),
    ]
    assert [c.title for c in result.parent_chunks] == ["Introduction", "Prior work", "Method", "Results"]
    assert all(c.text.startswith(c.title) for c in result.parent_chunks)
    assert result.verify()


def test_explicit_section_path_is_preserved_without_heading_inference():
    result = ChunkingEngine().split(document(ParsedBlock(
        block_id="b0", text="Experimental results.", section_path=("Paper", "Results"),
    )))
    assert result.child_chunks[0].section_path == ("Paper", "Results")
    assert result.child_chunks[0].title == "Results"


def test_parent_child_relationships_have_separate_continuous_indexes():
    result = split("方法。" * 100, child=13, parent=41)
    parents = {c.chunk_id: c for c in result.parent_chunks}
    for child in result.child_chunks:
        parent = parents[child.parent_chunk_id]
        assert parent.is_parent and parent.parent_chunk_id is None
        assert not child.is_parent
        assert child.text in parent.text
        assert child.section_path == parent.section_path
    assert [c.chunk_index for c in result.child_chunks] == list(range(len(result.child_chunks)))
    assert [c.chunk_index for c in result.parent_chunks] == list(range(len(result.parent_chunks)))
    assert set(parents) == {c.parent_chunk_id for c in result.child_chunks}


def test_pdf_page_range_and_source_spans_point_to_original_blocks():
    blocks = (
        ParsedBlock(block_id="p2", text="Page two content.", page_start=2, page_end=2),
        ParsedBlock(block_id="p3", text="Page three content.", page_start=3, page_end=3),
    )
    source = document(*blocks, page_count=4)
    result = ChunkingEngine().split(source, ChunkingConfig(child_max_tokens=12, parent_max_tokens=80))
    parent = result.parent_chunks[0]
    assert (parent.page_start, parent.page_end) == (2, 3)
    by_id = {b.block_id: b for b in blocks}
    for chunk in result.parent_chunks + result.child_chunks:
        assert chunk.source_locator.source == source.source
        assert chunk.source_locator.spans
        fragments = []
        for span in chunk.source_locator.spans:
            block = by_id[span.block_id]
            assert 0 <= span.char_start < span.char_end <= len(block.text)
            assert (span.page_start, span.page_end) == (block.page_start, block.page_end)
            fragments.append(block.text[span.char_start:span.char_end])
        assert compact("".join(fragments)) == compact(chunk.text)
    assert result.verify()


def test_table_and_formula_metadata_survive_splitting_and_json():
    table = TableMetadata(table_id="t1", caption="Accuracy", columns=("Method", "Score"), rows=(("RAG4", "0.9"),))
    formula = FormulaMetadata(formula_id="f1", latex=r"E=mc^2", label="(1)")
    result = ChunkingEngine().split(document(
        ParsedBlock(block_id="p", text="Prose surrounding structured objects."),
        ParsedBlock(block_id="t", kind="table", text="Method | Score\nRAG4 | 0.9", table=table),
        ParsedBlock(block_id="f", kind="formula", text="E = m c squared", formula=formula),
    ), ChunkingConfig(child_max_tokens=9, parent_max_tokens=80))
    assert len(result.parent_chunks) == 3
    assert result.parent_chunks[0].table_metadata == ()
    assert result.parent_chunks[1].table_metadata == (table,)
    assert result.parent_chunks[2].formula_metadata == (formula,)
    for chunk in result.child_chunks:
        block_ids = {s.block_id for s in chunk.source_locator.spans}
        assert chunk.table_metadata == ((table,) if "t" in block_ids else ())
        assert chunk.formula_metadata == ((formula,) if "f" in block_ids else ())
    restored = ChunkSet.model_validate_json(result.model_dump_json())
    assert restored == result
    assert restored.verify()


def test_repeated_runs_are_byte_for_byte_deterministic():
    first = split("研究方法。" * 30)
    second = split("研究方法。" * 30)
    assert first.model_dump_json() == second.model_dump_json()
    assert first.chunk_set_id == first.expected_id()
    assert first.stats.input_blocks == 1


def test_parsed_document_is_an_immutable_json_roundtrip_snapshot():
    source = document(ParsedBlock(block_id="b", text="Original text."))
    restored = ParsedDocument.model_validate_json(source.model_dump_json())
    assert restored == source
    with pytest.raises(ValidationError, match="frozen"):
        restored.parser_version = "mutated"
    with pytest.raises(ValidationError, match="frozen"):
        restored.blocks[0].text = "mutated"


@pytest.mark.parametrize("change", ["version", "budget", "tokenizer", "parser", "source"])
def test_input_identity_changes_when_any_semantic_revision_changes(change):
    original = document(ParsedBlock(block_id="b", text="A short unchanged text."))
    config = ChunkingConfig(child_max_tokens=40, parent_max_tokens=100)
    baseline = ChunkingEngine().split(original, config)
    engine = ChunkingEngine()
    if change == "version":
        config = config.model_copy(update={"chunking_version": "rag4-v2"})
    elif change == "budget":
        config = config.model_copy(update={"child_max_tokens": 41})
    elif change == "tokenizer":
        class RevisedCounter(CharacterTokenCounter):
            identity = "unicode-codepoint-v2"
        engine = ChunkingEngine(RevisedCounter())
    elif change == "parser":
        original = original.model_copy(update={"parser_version": "parser-v2"})
    else:
        original = original.model_copy(update={"source": SourceInfo(uri="upload://other-revision")})
    changed = engine.split(original, config)
    assert changed.input_id != baseline.input_id
    assert changed.chunk_set_id != baseline.chunk_set_id
    baseline_ids = {c.chunk_id for c in baseline.parent_chunks + baseline.child_chunks}
    changed_ids = {c.chunk_id for c in changed.parent_chunks + changed.child_chunks}
    assert baseline_ids.isdisjoint(changed_ids)
    assert changed.verify()


def test_integrity_check_rejects_tampered_chunk_content_and_stats():
    result = split("Original evidence.")
    tampered = result.model_copy(update={"child_chunks": (result.child_chunks[0].model_copy(update={"text": "Fabricated evidence."}),)})
    assert not tampered.verify()
    # Rehashing only the outer envelope must not bypass individual chunk hashes.
    tampered = tampered.model_copy(update={"chunk_set_id": tampered.expected_id()})
    assert not tampered.verify()
    bad_stats = result.model_copy(update={"stats": result.stats.model_copy(update={"child_count": 999})})
    bad_stats = bad_stats.model_copy(update={"chunk_set_id": bad_stats.expected_id()})
    assert not bad_stats.verify()


def test_integrity_check_rejects_rehashed_dangling_parent_reference():
    result = split("Original evidence.")
    child = result.child_chunks[0].model_copy(update={"parent_chunk_id": "missing-parent"})
    child = child.model_copy(update={"chunk_id": child.expected_id(result.input_id)})
    invalid = result.model_copy(update={"child_chunks": (child,)})
    invalid = invalid.model_copy(update={"chunk_set_id": invalid.expected_id()})
    assert not invalid.verify()


@pytest.mark.parametrize("blocks", [(), (ParsedBlock(block_id="empty", text=" \n\t "),)])
def test_empty_documents_have_valid_reproducible_empty_chunk_sets(blocks):
    result = ChunkingEngine().split(document(*blocks))
    assert result.parent_chunks == result.child_chunks == ()
    assert result.stats.input_blocks == len(blocks)
    assert result.stats.parent_count == result.stats.child_count == 0
    assert result.stats.parent_tokens == result.stats.child_tokens == 0
    assert result.verify()


@pytest.mark.parametrize("updates", [
    {"document_id": " "}, {"file_name": ""}, {"parser_version": ""},
    {"page_count": -1}, {"page_count": True}, {"blocks": [{"block_id": "x", "text": None}]},
])
def test_invalid_document_fields_are_rejected(updates):
    with pytest.raises(ValidationError):
        document(**updates)


def test_duplicate_block_ids_and_pages_outside_document_are_rejected():
    block = ParsedBlock(block_id="same", text="text", page_start=2, page_end=2)
    with pytest.raises(ValidationError, match="unique"):
        document(block, block)
    with pytest.raises(ValidationError, match="page_count"):
        document(block, page_count=1)


@pytest.mark.parametrize("updates", [
    {"kind": "heading"}, {"heading_level": 1},
    {"kind": "heading", "heading_level": 7},
    {"page_start": 1}, {"page_start": 2, "page_end": 1},
])
def test_invalid_block_structure_is_rejected(updates):
    with pytest.raises(ValidationError):
        ParsedBlock(block_id="b", text="Text", **updates)


@pytest.mark.parametrize("updates", [
    {"child_max_tokens": 0}, {"child_max_tokens": True},
    {"child_max_tokens": 20, "parent_max_tokens": 10}, {"chunking_version": " "},
])
def test_invalid_budget_or_version_is_rejected(updates):
    with pytest.raises(ValidationError):
        ChunkingConfig(**updates)


def test_empty_source_span_is_rejected():
    with pytest.raises(ValidationError):
        SourceSpan(block_id="b", char_start=3, char_end=3)


def test_engine_rejects_untyped_input():
    with pytest.raises(TypeError, match="ParsedDocument"):
        ChunkingEngine().split({"text": "untyped"})


@pytest.mark.parametrize("count", [-1, 1.5, True, "2", None])
def test_illegal_token_counter_results_fail_explicitly(count):
    class InvalidCounter:
        identity = "invalid-counter-v1"

        def count(self, text):
            return count

    with pytest.raises(ValueError, match="nonnegative integer"):
        ChunkingEngine(InvalidCounter()).split(document(ParsedBlock(block_id="b", text="text")))


def test_runtime_tokenizer_failure_is_not_silently_replaced_by_fallback(caplog):
    class BrokenTokenizer:
        def encode(self, text, *, add_special_tokens):
            raise RuntimeError("tokenizer unavailable during execution")

    engine = ChunkingEngine(TokenizerTokenCounter(BrokenTokenizer(), identity="broken@rev1"))
    with pytest.raises(RuntimeError, match="unavailable"):
        engine.split(document(ParsedBlock(block_id="b", text="text")))
    assert "chunking failed" in caplog.text
    assert "doc-paper" in caplog.text and "broken@rev1" in caplog.text


def test_no_tokenizer_uses_explicit_deterministic_character_fallback():
    result = split("中文abc🚀", child=3, parent=12)
    assert result.tokenizer_id == "unicode-codepoint-v1"
    assert [c.text for c in result.child_chunks] == ["中文a", "bc🚀"]
    assert result.stats.child_tokens == 6


def test_encode_tokenizer_controls_budget_and_disables_special_tokens():
    calls = []

    class ByteTokenizer:
        def encode(self, text, *, add_special_tokens):
            calls.append(add_special_tokens)
            return list(text.encode("utf-8"))

    engine = ChunkingEngine(TokenizerTokenCounter(ByteTokenizer(), identity="utf8-bytes@rev1"))
    text = "中英文abcdef🚀混合文本"
    result = engine.split(document(ParsedBlock(block_id="b", text=text)), ChunkingConfig(child_max_tokens=6, parent_max_tokens=15))
    assert "".join(c.text for c in result.child_chunks) == text
    assert all(c.token_count == len(c.text.encode("utf-8")) <= 6 for c in result.child_chunks)
    assert all(c.token_count <= 15 for c in result.parent_chunks)
    assert calls and not any(calls)
    assert result.verify()


def test_character_that_cannot_fit_token_budget_fails_without_truncation():
    class ExpensiveCounter:
        identity = "two-tokens-per-char-v1"

        def count(self, text):
            return len(text) * 2

    with pytest.raises(ValueError, match="cannot fit"):
        ChunkingEngine(ExpensiveCounter()).split(
            document(ParsedBlock(block_id="b", text="中")),
            ChunkingConfig(child_max_tokens=1, parent_max_tokens=2),
        )


def test_nonmonotone_token_counts_accept_merged_token():
    class MergingCounter:
        identity = "merging-v1"

        def count(self, text):
            return len(text.replace("AB", "x")) if len(text) > 1 else 2

    result = ChunkingEngine(MergingCounter()).split(
        document(ParsedBlock(block_id="b", text="AB")),
        ChunkingConfig(child_max_tokens=1, parent_max_tokens=3),
    )
    assert [c.text for c in result.child_chunks] == ["AB"]
    assert result.verify()


def test_nonmonotone_counter_searches_prefix_when_binary_search_finds_none():
    class MergingCounter:
        identity = "nonmonotone-v1"

        def count(self, text):
            return 1 if text == "ABCD" else len(text) * 3

    result = ChunkingEngine(MergingCounter()).split(
        document(ParsedBlock(block_id="b", text="ABCDABCD")),
        ChunkingConfig(child_max_tokens=1, parent_max_tokens=30),
    )
    assert [c.text for c in result.child_chunks] == ["ABCD", "ABCD"]


def test_code_chunks_preserve_indentation_and_newlines_exactly():
    text = "def f():\n    if True:\n        return 1\n    return 0"
    result = ChunkingEngine().split(
        document(ParsedBlock(block_id="b", text=text, kind="code")),
        ChunkingConfig(child_max_tokens=9, parent_max_tokens=25),
    )
    assert "".join(c.text for c in result.child_chunks) == text
    assert "".join(c.text for c in result.parent_chunks) == text


def test_verify_input_provenance():
    original = document(ParsedBlock(block_id="b", text="Original"))
    result = ChunkingEngine().split(original)
    assert result.verify(original)
    assert not result.verify(document(ParsedBlock(block_id="b", text="Changed")))


@pytest.mark.parametrize("pages", [{"page_start": 1}, {"page_start": 3, "page_end": 2}])
def test_invalid_source_pages_are_rejected(pages):
    with pytest.raises(ValidationError):
        SourceSpan(block_id="b", char_start=0, char_end=1, **pages)


def test_tokenizer_identity_must_be_explicit_and_nonblank():
    with pytest.raises(ValueError, match="identity"):
        TokenizerTokenCounter(object(), identity=" ")
    class AnonymousCounter(CharacterTokenCounter):
        identity = ""
    with pytest.raises(ValueError, match="identity"):
        ChunkingEngine(AnonymousCounter())


def test_rag3_split_blocks_golden_preserves_overlap_page_and_index_behavior():
    result = split_blocks([
        TextBlock(text="A" * 100 + "B" * 100, page=2),
        TextBlock(text="  第二页短文。  ", page=3),
        TextBlock(text="  "),
    ], chunk_size=100, overlap=10)
    assert [(c.text, c.page, c.chunk_index) for c in result] == [
        ("A" * 100, 2, 0),
        ("A" * 10 + "B" * 100, 2, 1),
        ("第二页短文。", 3, 2),
    ]
    assert len(result[1].text) == 110
