from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List


BASE_DIR = Path(__file__).resolve().parents[1]
from company.store import DB_PATH, authorize_user, initialize_company_store


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    initialize_company_store()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()

    if suffix in {".txt", ".md", ".csv", ".json"}:
        return data.decode("utf-8", errors="ignore")

    # Basic PDF support when pypdf is installed.
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(data))
            pages = []

            for page in reader.pages:
                pages.append(page.extract_text() or "")

            return "\n".join(pages)
        except Exception as exc:
            raise RuntimeError(
                f"PDF text extraction failed: {exc}"
            )

    raise ValueError(
        "Unsupported document type. Use PDF, TXT, MD, CSV or JSON."
    )


def _chunk_text(
    text: str,
    chunk_size: int = 1200,
    overlap: int = 150,
) -> List[str]:

    text = re.sub(r"\s+", " ", text or "").strip()

    if not text:
        return []

    chunks = []
    start = 0
    length = len(text)

    while start < length:
        end = min(
            start + chunk_size,
            length,
        )

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= length:
            break

        start = max(
            end - overlap,
            start + 1,
        )

    return chunks


def ingest_document(
    *,
    company_id: str,
    uploaded_by: str,
    title: str,
    filename: str,
    data: bytes,
    category: str = "",
    department: str = "",
    visibility: str = "company",
) -> Dict[str, Any]:

    authorize_user(company_id, uploaded_by, allowed_roles=["company_admin"])

    if not company_id:
        return {
            "status": "error",
            "message": "company_id is required.",
        }

    if not uploaded_by:
        return {
            "status": "error",
            "message": "uploaded_by is required.",
        }

    if not filename:
        return {
            "status": "error",
            "message": "filename is required.",
        }

    text = _extract_text(
        filename,
        data,
    )

    chunks = _chunk_text(text)

    if not chunks:
        return {
            "status": "error",
            "message": "The uploaded document contains no readable text.",
        }

    now = _utc_now()

    storage_dir = BASE_DIR / "data" / "documents" / company_id
    storage_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    safe_name = re.sub(
        r"[^A-Za-z0-9._-]",
        "_",
        filename,
    )

    storage_path = storage_dir / safe_name
    storage_path.write_bytes(data)

    with _connect() as conn:

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO documents (
                company_id,
                title,
                filename,
                document_type,
                storage_path,
                category,
                department,
                visibility,
                status,
                version,
                uploaded_by,
                published_at,
                expires_at,
                metadata_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                title or filename,
                filename,
                Path(filename).suffix.lower().lstrip("."),
                str(storage_path),
                category,
                department,
                visibility,
                "active",
                1,
                uploaded_by,
                now,
                None,
                "{}",
                now,
                now,
            ),
        )

        document_id = cursor.lastrowid

        for index, chunk in enumerate(chunks):

            cursor.execute(
                """
                INSERT INTO document_chunks (
                    company_id,
                    document_id,
                    chunk_index,
                    content,
                    embedding_ref,
                    metadata_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    document_id,
                    index,
                    chunk,
                    "",
                    "{}",
                    now,
                ),
            )

        conn.commit()

    return {
        "status": "success",
        "document_id": document_id,
        "title": title or filename,
        "filename": filename,
        "chunk_count": len(chunks),
        "storage_path": str(storage_path),
        "message": (
            f"Document uploaded successfully with "
            f"{len(chunks)} knowledge chunk(s)."
        ),
    }


def list_documents(
    company_id: str,
    user_id: str,
) -> List[Dict[str, Any]]:

    authorize_user(company_id, user_id, allowed_roles=["company_admin"])

    if not company_id:
        return []

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                document_id,
                title,
                filename,
                category,
                department,
                visibility,
                status,
                version,
                uploaded_by,
                created_at,
                updated_at
            FROM documents
            WHERE company_id = ?
            ORDER BY updated_at DESC
            """,
            (company_id,),
        ).fetchall()

    return [dict(row) for row in rows]
