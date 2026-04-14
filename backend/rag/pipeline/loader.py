"""
pipeline/loader.py
문서 로드 및 청킹

지원 형식: .md, .txt, .pdf
청킹 전략: 헤더 기반 청킹 → 크기 초과 시 재귀 분할
"""

import hashlib
import os
import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """청크 단위 문서"""
    chunk_id:  str          # MD5 해시 기반 고유 ID
    text:      str          # 청크 텍스트
    source:    str          # 원본 파일 경로
    domain:    str          # 도메인 분류 (ecommerce / ga4 / ...)
    heading:   str          # 소속 헤더 (없으면 빈 문자열)
    metadata:  dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.chunk_id:
            raw = f"{self.source}::{self.heading}::{self.text[:100]}"
            self.chunk_id = hashlib.md5(raw.encode()).hexdigest()


# ── 마크다운 헤더 기반 청킹 ────────────────────────────────────────────────────
def _split_by_headers(text: str) -> list[tuple[str, str]]:
    """
    마크다운을 헤더(## / ###) 단위로 분할.
    Returns: [(heading, section_text), ...]
    """
    pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        return [("", text.strip())]

    sections = []
    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start   = match.start()
        end     = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body    = text[start:end].strip()
        if body:
            sections.append((heading, body))

    return sections


def _split_by_size(text: str, max_chars: int, overlap: int) -> list[str]:
    """
    텍스트를 max_chars 크기로 분할. 문장 경계 우선, overlap 포함.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start  = 0
    while start < len(text):
        end = start + max_chars
        if end >= len(text):
            chunks.append(text[start:])
            break

        # 문장 경계 역탐색 (마침표/줄바꿈)
        boundary = max(
            text.rfind(".", start, end),
            text.rfind("\n", start, end),
        )
        if boundary > start:
            end = boundary + 1

        chunks.append(text[start:end].strip())
        start = end - overlap  # overlap 적용

    return [c for c in chunks if c.strip()]


# ── 파일 로더 ─────────────────────────────────────────────────────────────────
def _load_markdown(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _load_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _load_pdf(path: str) -> str:
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        return "\n\n".join(pages)
    except ImportError:
        raise ImportError("PDF 로딩에 pdfplumber 필요: pip install pdfplumber")


_LOADERS = {
    ".md":  _load_markdown,
    ".txt": _load_text,
    ".pdf": _load_pdf,
}


def _infer_domain(filepath: str, docs_root: str) -> str:
    """파일 경로에서 도메인 추출 (documents/{domain}/...)"""
    rel = os.path.relpath(filepath, docs_root)
    parts = rel.split(os.sep)
    return parts[0] if len(parts) > 1 else "general"


# ── 메인 API ──────────────────────────────────────────────────────────────────
def load_and_chunk(
    docs_root: str,
    max_chars: int = 1000,
    overlap:   int = 100,
) -> list[Chunk]:
    """
    docs_root 하위의 모든 문서를 재귀 탐색해 Chunk 목록 반환.

    Args:
        docs_root:  문서 루트 디렉터리
        max_chars:  청크 최대 문자 수 (헤더 섹션이 이 크기 초과 시 재분할)
        overlap:    청크 간 겹치는 문자 수 (문맥 연속성 유지)
    """
    chunks: list[Chunk] = []

    for dirpath, _, filenames in os.walk(docs_root):
        for fname in sorted(filenames):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _LOADERS:
                continue

            fpath  = os.path.join(dirpath, fname)
            domain = _infer_domain(fpath, docs_root)

            try:
                text = _LOADERS[ext](fpath)
            except Exception as e:
                print(f"[WARN] 파일 로드 실패 {fpath}: {e}")
                continue

            sections = _split_by_headers(text)

            for heading, section in sections:
                sub_chunks = _split_by_size(section, max_chars, overlap)
                for i, sub in enumerate(sub_chunks):
                    if not sub.strip():
                        continue
                    raw_id = f"{fpath}::{heading}::{i}::{sub[:80]}"
                    chunks.append(Chunk(
                        chunk_id = hashlib.md5(raw_id.encode()).hexdigest(),
                        text     = sub,
                        source   = os.path.relpath(fpath, docs_root),
                        domain   = domain,
                        heading  = heading,
                        metadata = {
                            "filename":    fname,
                            "domain":      domain,
                            "heading":     heading,
                            "chunk_index": i,
                        },
                    ))

    return chunks