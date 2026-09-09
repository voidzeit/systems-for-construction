"""Optional PDF document connector.

The core stays dependency-free. When the optional ``pypdf`` package is
installed, this adapter exposes each page as a Project World document element
with page provenance. A missing optional dependency fails explicitly instead of
silently dropping document content.
"""

from __future__ import annotations

from pathlib import Path
import hashlib

from .models import ProjectWorld, WorldElement


def load_pdf(path: str | Path) -> ProjectWorld:
    source = Path(path)
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError("PDF support requires the optional 'pypdf' package") from error
    source_id = f"pdf:{hashlib.sha256(source.read_bytes()).hexdigest()[:16]}"
    reader = PdfReader(str(source))
    elements = []
    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        element_id = f"{source_id}:page:{number}"
        elements.append(WorldElement(
            element_id=element_id,
            kind="pdf_page",
            properties={"page_number": number, "text": text},
            evidence_by_property={"text": (f"{element_id}:text",)},
            source_id=source_id,
        ))
    return ProjectWorld(
        project_id=source_id,
        elements=tuple(elements),
        metadata={"connector": "sfc.pdf", "pageCount": len(elements)},
    )

