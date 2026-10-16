"""Safe read/preview helpers for uploaded employee and project documents."""
from __future__ import annotations

import base64
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def render_document_preview(st: Any, *, file_name: str, data: bytes, content_type: str = "", key: str = "preview") -> None:
    name = str(file_name or "document")
    ext = Path(name).suffix.casefold()
    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        st.image(data, caption=name, width="stretch")
        return
    if ext == ".pdf" or content_type == "application/pdf":
        encoded = base64.b64encode(data).decode("ascii")
        # A sandboxed iframe preview is isolated from the app DOM.
        st.components.v1.html(
            f'<iframe title="Document preview" src="data:application/pdf;base64,{encoded}" '
            'width="100%" height="620px" style="border:1px solid #ddd;border-radius:8px"></iframe>',
            height=630,
            scrolling=True,
        )
        return
    if ext in {".txt", ".md", ".csv", ".json", ".py", ".log", ".yaml", ".yml"}:
        text = data[:300_000].decode("utf-8", errors="replace")
        st.code(text, language={".py": "python", ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".csv": "csv"}.get(ext, "text"))
        if len(data) > 300_000:
            st.caption("Preview truncated to the first 300 KB. Download the complete file to read the remainder.")
        return
    if ext in {".docx", ".pptx"}:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if ext == ".docx":
                    xml_names = ["word/document.xml"]
                else:
                    xml_names = sorted(n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
                pieces = []
                for xml_name in xml_names:
                    if xml_name not in archive.namelist():
                        continue
                    root = ET.fromstring(archive.read(xml_name))
                    pieces.extend(item.text or "" for item in root.iter() if item.tag.endswith("}t"))
            text = "\n".join(pieces).strip()
            if text:
                st.text_area("Extracted text preview", value=text[:100_000], height=300, disabled=True, key=f"{key}_office_text")
                if len(text) > 100_000:
                    st.caption("Preview truncated; download the complete document for the rest.")
            else:
                st.info("This file did not contain extractable text. Download it to open in its native application.")
        except (KeyError, zipfile.BadZipFile, ET.ParseError, OSError):
            st.info("Preview is unavailable for this document. Download it to open in its native application.")
        return
    st.info("Inline preview is not available for this file type. Use Download to open it in its native application.")
