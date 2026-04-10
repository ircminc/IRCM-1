"""
Base EDI parser: reads envelope, detects TX type, dispatches to the correct parser.
"""
from __future__ import annotations
import io
from pathlib import Path
from typing import Any

from .envelope import detect_delimiters, parse_isa, parse_gs, ISAEnvelope, GSGroup
from .segment_reader import iter_segments


TX_TYPE_MAP = {
    "837": "837P",
    "835": "835",
    "270": "270",
    "271": "271",
    "276": "276",
    "277": "277",
    "834": "834",
    "820": "820",
}


def detect_tx_type(source: Path | io.BytesIO | str) -> str:
    """
    Reads the GS01 functional identifier from the first GS segment to determine TX type.
    Returns one of: '837P','835','270','271','276','277','834','820', or 'UNKNOWN'.
    """
    element_sep, component_sep, segment_term = _get_delimiters(source)
    for seg in iter_segments(source, element_sep, segment_term):
        if not seg:
            continue
        seg_id = seg[0].upper()
        if seg_id == "ST" and len(seg) > 1:
            ts_id = seg[1][:3]
            return TX_TYPE_MAP.get(ts_id, f"TX{seg[1]}")
    return "UNKNOWN"


def _get_delimiters(source: Path | io.BytesIO | str) -> tuple[str, str, str]:
    if isinstance(source, (str, Path)):
        with open(source, "rb") as f:
            raw = f.read(106)
    elif isinstance(source, (io.BytesIO, io.RawIOBase, io.BufferedIOBase)):
        pos = source.tell()
        raw = source.read(106)
        source.seek(pos)
    else:
        raw = b""
    return detect_delimiters(raw)


def parse_edi_file(source: Path | io.BytesIO | str) -> dict[str, Any]:
    """
    Master entry point. Returns a dict with keys:
      tx_type, envelope (ISAEnvelope), groups (list[GSGroup]), data (parsed domain objects)
    """
    element_sep, component_sep, segment_term = _get_delimiters(source)
    segments = list(iter_segments(source, element_sep, segment_term))

    envelope = ISAEnvelope(
        element_sep=element_sep,
        component_sep=component_sep,
        segment_term=segment_term,
    )
    groups: list[GSGroup] = []
    tx_type = "UNKNOWN"
    current_group: GSGroup | None = None

    for seg in segments:
        if not seg:
            continue
        seg_id = seg[0].upper()
        if seg_id == "ISA":
            envelope = parse_isa(seg)
            envelope.element_sep = element_sep
            envelope.component_sep = component_sep
            envelope.segment_term = segment_term
        elif seg_id == "GS":
            current_group = parse_gs(seg)
            groups.append(current_group)
        elif seg_id == "ST" and tx_type == "UNKNOWN":
            ts_id = seg[1][:3] if len(seg) > 1 else ""
            tx_type = TX_TYPE_MAP.get(ts_id, f"TX{ts_id}")

    # Dispatch to specific parser
    data = _dispatch(tx_type, segments, element_sep, component_sep, segment_term)

    return {
        "tx_type": tx_type,
        "envelope": envelope,
        "groups": groups,
        "data": data,
        "raw_segments": segments,
    }


def _dispatch(tx_type: str, segments: list[list[str]], es: str, cs: str, st: str) -> Any:
    if tx_type == "837P":
        from .tx_837p import parse_837p
        return parse_837p(segments, es, cs)
    elif tx_type == "835":
        from .tx_835 import parse_835
        return parse_835(segments, es, cs)
    elif tx_type == "270":
        from .tx_270 import parse_270
        return parse_270(segments, es, cs)
    elif tx_type == "271":
        from .tx_271 import parse_271
        return parse_271(segments, es, cs)
    elif tx_type == "276":
        from .tx_276 import parse_276
        return parse_276(segments, es, cs)
    elif tx_type == "277":
        from .tx_277 import parse_277
        return parse_277(segments, es, cs)
    elif tx_type == "834":
        from .tx_834 import parse_834
        return parse_834(segments, es, cs)
    elif tx_type == "820":
        from .tx_820 import parse_820
        return parse_820(segments, es, cs)
    return {}
