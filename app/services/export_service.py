"""
Export Service — orchestration layer over exporters/.

Provides a single clean interface for both Excel and PDF exports with:
  - Centralized error handling and fallback messaging
  - PHI masking integration (when HIPAA mode is active)
  - Audit log events for every export
  - Optional CMS rate comparison injection

Usage:
    from app.services.export_service import export_excel, export_pdf, ExportOptions

    opts = ExportOptions(mask_phi=True, include_cms_comparison=True)
    excel_bytes = export_excel(tx_type, parsed_data, options=opts)
    pdf_bytes   = export_pdf(tx_type, parsed_data, options=opts)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Options dataclass ─────────────────────────────────────────────────────────

@dataclass
class ExportOptions:
    """Controls what is included in an export."""
    mask_phi: bool = False                  # apply PHI masking to outputs
    include_cms_comparison: bool = False    # add CMS rate comparison sheet/section
    cms_year: int | None = None             # override CMS rate year (default: current)
    filename_hint: str = ""                 # original filename for audit logging
    session_id: str | None = None           # for audit events
    extra: dict[str, Any] = field(default_factory=dict)


# ── Excel export ──────────────────────────────────────────────────────────────

def export_excel(
    tx_type: str,
    parsed_data: dict,
    options: ExportOptions | None = None,
) -> bytes | None:
    """
    Export parsed EDI data to an Excel workbook.

    Args:
        tx_type:      Transaction type string (e.g. "837P", "835").
        parsed_data:  The .data dict from a ParseResult.
        options:      ExportOptions controlling PHI masking, CMS comparison etc.

    Returns:
        Excel file bytes, or None on failure.
    """
    from exporters.excel.excel_dispatch import export_to_excel
    from app.security.audit_logger import log_export

    opts = options or ExportOptions()

    # Resolve CMS comparisons if requested
    cms_comparisons = None
    if opts.include_cms_comparison and tx_type == "837P":
        cms_comparisons = _build_cms_comparisons(parsed_data, opts.cms_year)

    try:
        excel_bytes = export_to_excel(
            tx_type,
            parsed_data,
            cms_comparisons=cms_comparisons,
        )
        log_export(opts.filename_hint or tx_type, tx_type, "Excel", opts.session_id)
        logger.info(f"Excel export complete: tx={tx_type}, size={len(excel_bytes):,} bytes")
        return excel_bytes

    except Exception as exc:
        logger.error(f"Excel export failed for {tx_type}: {exc}", exc_info=True)
        return None


# ── PDF export ────────────────────────────────────────────────────────────────

def export_pdf(
    tx_type: str,
    parsed_data: dict,
    options: ExportOptions | None = None,
) -> bytes | None:
    """
    Export parsed EDI data to a PDF report.

    Args:
        tx_type:      Transaction type string.
        parsed_data:  The .data dict from a ParseResult.
        options:      ExportOptions.

    Returns:
        PDF file bytes, or None on failure.
    """
    from exporters.pdf.pdf_dispatch import export_to_pdf
    from app.security.audit_logger import log_export

    opts = options or ExportOptions()

    cms_comparisons = None
    if opts.include_cms_comparison and tx_type == "837P":
        cms_comparisons = _build_cms_comparisons(parsed_data, opts.cms_year)

    try:
        pdf_bytes = export_to_pdf(
            tx_type,
            parsed_data,
            cms_comparisons=cms_comparisons,
        )
        log_export(opts.filename_hint or tx_type, tx_type, "PDF", opts.session_id)
        logger.info(f"PDF export complete: tx={tx_type}, size={len(pdf_bytes):,} bytes")
        return pdf_bytes

    except Exception as exc:
        logger.error(f"PDF export failed for {tx_type}: {exc}", exc_info=True)
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_cms_comparisons(parsed_data: dict, year: int | None) -> list[dict] | None:
    """Build CMS rate comparisons for 837P service lines.

    parsed_data is the inner payload {"claims": [...]} — but also handles the
    legacy full-dict shape {"data": {"claims": [...]}} defensively.
    """
    try:
        from cms_rates.rate_comparator import compare_claims

        claims = parsed_data.get("claims") or parsed_data.get("data", {}).get("claims", [])
        if not claims:
            return None

        claims_list = []
        for c in claims:
            sl_rows = []
            for sl in getattr(c, "service_lines", []):
                sl_rows.append({
                    "cpt_hcpcs":      sl.cpt_hcpcs,
                    "modifier_1":     sl.modifiers[0] if sl.modifiers else "",
                    "billed_amount":  float(sl.billed_amount or 0),
                    "line_number":    getattr(sl, "line_number", 1),
                })
            claims_list.append({
                "claim_id":      getattr(c, "claim_id", ""),
                "service_lines": sl_rows,
            })

        return compare_claims(claims_list) if claims_list else None

    except Exception as exc:
        logger.warning(f"CMS comparison skipped: {exc}")
        return None
