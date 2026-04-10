"""
Streaming EDI segment reader. Yields each segment as a list[str] of elements.
Works against file paths or BytesIO objects safely for large files.
"""
from __future__ import annotations
import io
from pathlib import Path
from typing import Iterator


def iter_segments(
    source: Path | io.BytesIO | str,
    element_sep: str = "*",
    segment_term: str = "~",
    chunk_size: int = 65536,
) -> Iterator[list[str]]:
    """
    Generator that reads EDI data in chunks and yields one segment at a time
    as a list of element strings. Handles segment terminators mid-chunk.
    """
    buffer = ""

    def _iter_chunks():
        if isinstance(source, (str, Path)):
            with open(source, "r", encoding="ascii", errors="replace") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        elif isinstance(source, (io.BytesIO, io.RawIOBase, io.BufferedIOBase)):
            source.seek(0)
            while True:
                raw = source.read(chunk_size)
                if not raw:
                    break
                yield raw.decode("ascii", errors="replace")

    for chunk in _iter_chunks():
        buffer += chunk
        while segment_term in buffer:
            seg_text, buffer = buffer.split(segment_term, 1)
            seg_text = seg_text.strip()
            if seg_text:
                elements = seg_text.split(element_sep)
                yield elements

    # Flush any remaining content (file missing trailing terminator)
    if buffer.strip():
        elements = buffer.strip().split(element_sep)
        if elements and elements[0]:
            yield elements


def read_all_segments(
    source: Path | io.BytesIO | str,
    element_sep: str = "*",
    segment_term: str = "~",
) -> list[list[str]]:
    """Non-streaming version for smaller files or testing."""
    return list(iter_segments(source, element_sep, segment_term))
