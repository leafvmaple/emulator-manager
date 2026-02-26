"""Rename template engine — parses template expressions and generates filenames."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.utils import sanitize_filename


@dataclass
class RenameToken:
    """A single template variable definition."""

    key: str
    description: str


# All built-in template variables
BUILTIN_TOKENS: dict[str, str] = {
    "title": "标题（跟随应用语言）",
    "title_zh": "中文名",
    "title_en": "英文名",
    "title_ja": "日文名",
    "title_rom": "ROM 内嵌标题",
    "title_id": "Title ID / 序列号",
    "platform": "平台",
    "region": "区域",
    "languages": "支持语言",
    "version": "版本号",
    "file_type": "文件类型 (base/update/dlc)",
    "content_type": "容器格式 (nsp/xci/...)",
    "publisher": "发行商",
    "genre": "游戏类型",
    "ext": "原始扩展名",
    "seq": "序号",
    "crc32": "CRC32 哈希",
}

# Regex patterns for template parsing
_VAR_PATTERN = re.compile(r"\{([^}]+)\}")
_FALLBACK_PATTERN = re.compile(r"^([\w]+(?:\|[\w]+)+)$")
_CONDITIONAL_PATTERN = re.compile(r"^\?(\w+):(.+)$")
_SEQ_PATTERN = re.compile(r"^seq(?::(\d+))?$")


class RenameEngine:
    """
    Template-based rename engine.

    Template syntax:
      {title_zh}                  — simple variable substitution
      {title_zh|title_en|title_ja} — fallback chain: first non-empty wins
      {?version:v{version}}      — conditional: only include if 'version' has a value
      {seq:3}                    — zero-padded sequence number (001, 002, ...)

    Example templates:
      "{title_zh} [{title_id}][v{version}].{ext}"
        → "塞尔达传说：王国之泪 [0100F2C0115B6000][v1.2.0].nsp"

      "{title_en} ({region}) ({file_type}).{ext}"
        → "The Legend of Zelda Tears of the Kingdom (Japan) (base).xci"
    """

    def __init__(self) -> None:
        self._custom_tokens: dict[str, RenameToken] = {}

    def register_token(self, token: RenameToken) -> None:
        """Register a custom variable."""
        self._custom_tokens[token.key] = token

    def preview(self, template: str, context: dict[str, str], seq: int = 0) -> str:
        """Preview a single rename result."""
        return self._resolve_template(template, context, seq)

    def batch_preview(
        self,
        template: str,
        items: list[dict[str, str]],
    ) -> list[tuple[str, str]]:
        """
        Batch preview rename results.

        Returns: [(original_filename, new_filename), ...]
        """
        results: list[tuple[str, str]] = []
        for i, ctx in enumerate(items):
            original = Path(ctx.get("_rom_path", "")).name if "_rom_path" in ctx else ""
            new_name = self._resolve_template(template, ctx, seq=i + 1)
            results.append((original, new_name))
        return results

    def detect_conflicts(self, results: list[tuple[str, str]]) -> list[str]:
        """Detect duplicate new filenames in batch results."""
        seen: dict[str, list[str]] = {}
        for original, new_name in results:
            key = new_name.lower()
            if key not in seen:
                seen[key] = []
            seen[key].append(original)

        conflicts: list[str] = []
        for new_name_lower, originals in seen.items():
            if len(originals) > 1:
                conflicts.append(
                    f"'{originals[0]}' 和 '{originals[1]}' 等 {len(originals)} 个文件"
                    f"将重命名为相同的文件名"
                )
        return conflicts

    def _resolve_template(self, template: str, context: dict[str, str], seq: int = 0) -> str:
        """Core template resolution logic."""

        def replace_match(match: re.Match[str]) -> str:
            expr = match.group(1)

            # Sequence: {seq} or {seq:3}
            seq_m = _SEQ_PATTERN.match(expr)
            if seq_m:
                width = int(seq_m.group(1)) if seq_m.group(1) else 1
                return str(seq).zfill(width)

            # Conditional: {?version:v{version}}
            cond_m = _CONDITIONAL_PATTERN.match(expr)
            if cond_m:
                cond_key = cond_m.group(1)
                cond_body = cond_m.group(2)
                if context.get(cond_key):
                    # Recursively resolve the body
                    return self._resolve_template(cond_body, context, seq)
                return ""

            # Fallback: {title_zh|title_en|title_ja}
            fallback_m = _FALLBACK_PATTERN.match(expr)
            if fallback_m:
                keys = expr.split("|")
                for key in keys:
                    val = context.get(key, "")
                    if val:
                        return str(val)
                return ""

            # Simple variable
            return context.get(expr, "")

        result = _VAR_PATTERN.sub(replace_match, template)
        return sanitize_filename(result)
