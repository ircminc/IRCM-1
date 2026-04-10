"""Dispatch function to export any TX type to Excel bytes."""
from __future__ import annotations


def export_to_excel(tx_type: str, parsed_data: dict, cms_comparisons: list | None = None) -> bytes:
    """
    Routes to the correct Excel exporter based on TX type.
    Returns raw .xlsx bytes ready for download.
    """
    if tx_type == "837P":
        from .excel_837p import export_837p
        return export_837p(parsed_data, cms_comparisons)
    elif tx_type == "835":
        from .excel_835 import export_835
        return export_835(parsed_data)
    elif tx_type == "270":
        from .excel_270_271 import export_270
        return export_270(parsed_data)
    elif tx_type == "271":
        from .excel_270_271 import export_271
        return export_271(parsed_data)
    elif tx_type == "276":
        from .excel_276_277 import export_276
        return export_276(parsed_data)
    elif tx_type == "277":
        from .excel_276_277 import export_277
        return export_277(parsed_data)
    elif tx_type == "834":
        from .excel_834 import export_834
        return export_834(parsed_data)
    elif tx_type == "820":
        from .excel_820 import export_820
        return export_820(parsed_data)
    else:
        raise ValueError(f"No Excel exporter for TX type: {tx_type}")
