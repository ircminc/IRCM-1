"""Route TX types to the correct PDF exporter."""
from __future__ import annotations


def export_to_pdf(tx_type: str, parsed_data: dict, cms_comparisons: list | None = None) -> bytes:
    if tx_type == "837P":
        from .pdf_837p import export_pdf_837p
        return export_pdf_837p(parsed_data, cms_comparisons)
    elif tx_type == "835":
        from .pdf_835 import export_pdf_835
        return export_pdf_835(parsed_data)
    else:
        # Generic PDF for other TX types — just render the summary dict
        from reportlab.platypus import Paragraph, Spacer
        from .base_pdf import get_styles, build_pdf, cover_block
        from datetime import datetime
        styles = get_styles()
        story  = cover_block(
            title=f"{tx_type} Transaction Report",
            subtitle="",
            tx_type=tx_type,
            generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        story.append(Paragraph("Export to Excel for full details of this transaction type.", styles["Body9"]))
        return build_pdf(story, title=f"{tx_type} Report")
