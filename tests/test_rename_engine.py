"""Tests for the RenameEngine template system."""

from __future__ import annotations

import pytest

from app.core.rename_engine import RenameEngine


@pytest.fixture
def engine() -> RenameEngine:
    return RenameEngine()


class TestSimpleTokens:
    def test_basic_substitution(self, engine: RenameEngine) -> None:
        result = engine.preview("{title_en}", {"title_en": "Zelda"})
        assert result == "Zelda"

    def test_missing_token_returns_empty(self, engine: RenameEngine) -> None:
        result = engine.preview("{title_en}", {})
        assert result == ""

    def test_static_text_preserved(self, engine: RenameEngine) -> None:
        result = engine.preview("Game - {title_en}", {"title_en": "Zelda"})
        assert result == "Game - Zelda"


class TestFallbackChain:
    def test_first_available(self, engine: RenameEngine) -> None:
        result = engine.preview(
            "{title_zh|title_en|title_ja}",
            {"title_zh": "塞尔达", "title_en": "Zelda"},
        )
        assert result == "塞尔达"

    def test_second_fallback(self, engine: RenameEngine) -> None:
        result = engine.preview(
            "{title_zh|title_en|title_ja}",
            {"title_en": "Zelda"},
        )
        assert result == "Zelda"

    def test_all_missing(self, engine: RenameEngine) -> None:
        result = engine.preview("{title_zh|title_en}", {})
        assert result == ""


class TestConditional:
    def test_conditional_present(self, engine: RenameEngine) -> None:
        result = engine.preview(
            "{title_en}{?version: [v{version}]}",
            {"title_en": "Zelda", "version": "1.2.0"},
        )
        assert result == "Zelda [v1.2.0]"

    def test_conditional_absent(self, engine: RenameEngine) -> None:
        result = engine.preview(
            "{title_en}{?version: [v{version}]}",
            {"title_en": "Zelda"},
        )
        assert result == "Zelda"


class TestSequence:
    def test_sequence_numbering(self, engine: RenameEngine) -> None:
        tokens_list = [{"title_en": "Zelda"}] * 3
        results = engine.batch_preview("{title_en} {seq:3}", tokens_list)
        assert results == ["Zelda 001", "Zelda 002", "Zelda 003"]


class TestConflictDetection:
    def test_no_conflicts(self, engine: RenameEngine) -> None:
        tokens_list = [
            {"title_en": "A"},
            {"title_en": "B"},
        ]
        conflicts = engine.detect_conflicts("{title_en}", tokens_list)
        assert conflicts == {}

    def test_with_conflicts(self, engine: RenameEngine) -> None:
        tokens_list = [
            {"title_en": "Same"},
            {"title_en": "Same"},
        ]
        conflicts = engine.detect_conflicts("{title_en}", tokens_list)
        assert "Same" in conflicts
        assert len(conflicts["Same"]) == 2
