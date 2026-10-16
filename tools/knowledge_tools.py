from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from company.updates_service import (
    list_updates,
    search_updates,
)


# ============================================================
# DATABASE
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[1]
from company.store import DB_PATH, initialize_company_store


def _connect():
    initialize_company_store()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# HELPERS
# ============================================================

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None

    try:
        text = str(value).strip()

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        parsed = datetime.fromisoformat(text)

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed
    except Exception:
        return None


def _document_is_current(row: sqlite3.Row) -> bool:
    status = str(
        row["status"] or "active"
    ).strip().lower()

    if status != "active":
        return False

    now = _utc_now()

    published_at = _parse_datetime(
        row["published_at"]
    )

    if published_at and published_at > now:
        return False

    expires_at = _parse_datetime(
        row["expires_at"]
    )

    if expires_at and expires_at <= now:
        return False

    return True


def _tokenize(text: str) -> List[str]:
    return [
        token
        for token in re.findall(
            r"[a-zA-Z0-9_]+",
            str(text or "").lower(),
        )
        if len(token) >= 2
    ]


def _permission_matches(
    permission: sqlite3.Row,
    *,
    user_id: str,
    user_role: str,
    department: str,
) -> bool:

    permission_user = str(
        permission["user_id"] or ""
    ).strip()

    permission_role = str(
        permission["role"] or ""
    ).strip().lower()

    permission_department = str(
        permission["department"] or ""
    ).strip().lower()

    if permission_user:
        return permission_user == user_id

    if (
        permission_role
        and permission_role == user_role.lower()
    ):
        return True

    if (
        permission_department
        and permission_department == department.lower()
    ):
        return True

    return False


def _document_is_accessible(
    conn,
    document: sqlite3.Row,
    *,
    user_id: str,
    user_role: str,
    department: str,
) -> bool:

    document_id = int(
        document["document_id"]
    )

    permission_rows = conn.execute(
        """
        SELECT
            company_id,
            document_id,
            role,
            department,
            user_id
        FROM document_permissions
        WHERE company_id = ?
          AND document_id = ?
        """,
        (
            document["company_id"],
            document_id,
        ),
    ).fetchall()

    visibility = str(
        document["visibility"] or "company"
    ).strip().lower()

    # --------------------------------------------------------
    # Explicit permission rows are restrictive.
    # At least one applicable permission must match.
    # --------------------------------------------------------

    if permission_rows:

        return any(
            _permission_matches(
                permission,
                user_id=user_id,
                user_role=user_role,
                department=department,
            )
            for permission in permission_rows
        )

    # --------------------------------------------------------
    # No explicit permission rows.
    # Use document visibility.
    # --------------------------------------------------------

    if visibility in {
        "company",
        "public",
    }:
        return True

    if visibility in {
        "department",
        "department_only",
    }:
        return bool(
            department
            and str(
                document["department"] or ""
            ).strip().lower()
            == department.lower()
        )

    if visibility in {
        "role",
        "role_only",
    }:

        metadata = document["metadata_json"] or ""

        return (
            user_role.lower()
            in metadata.lower()
        )

    if visibility in {
        "private",
        "user",
        "user_only",
    }:
        uploaded_by = str(
            document["uploaded_by"] or ""
        ).strip()

        return bool(
            uploaded_by
            and uploaded_by == user_id
        )

    # Unknown visibility is denied by default.
    return False


def _score_document(
    query_tokens: List[str],
    *,
    title: str,
    category: str,
    department: str,
    content: str,
) -> int:

    if not query_tokens:
        return 0

    title_text = str(title or "").lower()
    category_text = str(category or "").lower()
    department_text = str(department or "").lower()
    content_text = str(content or "").lower()

    score = 0

    for token in query_tokens:

        if token in title_text:
            score += 10

        if token in category_text:
            score += 6

        if token in department_text:
            score += 4

        # Count content occurrences, but cap the
        # contribution so one document cannot dominate
        # only because a word is repeated many times.
        occurrences = content_text.count(token)

        score += min(
            occurrences,
            5,
        )

    return score


def _make_snippet(
    content: str,
    query_tokens: List[str],
    max_length: int = 500,
) -> str:

    text = str(
        content or ""
    ).strip()

    if len(text) <= max_length:
        return text

    lower = text.lower()

    start = 0

    for token in query_tokens:

        position = lower.find(
            token.lower()
        )

        if position >= 0:
            start = max(
                0,
                position - 120,
            )
            break

    snippet = text[
        start:start + max_length
    ].strip()

    if start > 0:
        snippet = "..." + snippet

    if start + max_length < len(text):
        snippet += "..."

    return snippet


# ============================================================
# REAL KNOWLEDGE SEARCH
# ============================================================

def search_knowledge(
    details: Optional[Dict[str, Any]] = None,
    message: str = "",
) -> Dict[str, Any]:

    details = details or {}

    # --------------------------------------------------------
    # Resolve query
    # --------------------------------------------------------

    query = str(
        details.get("query")
        or details.get("search_query")
        or message
        or ""
    ).strip()

    # --------------------------------------------------------
    # Resolve tenant / user context
    # --------------------------------------------------------

    company_id = str(
        details.get("company_id")
        or ""
    ).strip()

    user_id = str(
        details.get("user_id")
        or ""
    ).strip()

    user_role = str(
        details.get("user_role")
        or "employee"
    ).strip()

    department = str(
        details.get("department")
        or ""
    ).strip()

    # --------------------------------------------------------
    # Required tenant boundary
    # --------------------------------------------------------

    if not company_id:
        return {
            "status": "error",
            "executed": False,
            "message": (
                "Knowledge search requires a "
                "company_id for tenant isolation."
            ),
            "request_type": "knowledge_search",
        }

    try:
        from company.store import authorize_user
        authenticated_user = authorize_user(company_id, user_id)
    except (PermissionError, ValueError) as exc:
        return {"status": "permission_denied", "executed": False, "message": str(exc), "request_type": "knowledge_search"}
    user_role = str(authenticated_user.get("role") or "employee")
    department = str(authenticated_user.get("department") or "")

    if not query:
        return {
            "status": "no_result",
            "executed": True,
            "message": (
                "Please provide a knowledge search query."
            ),
            "request_type": "knowledge_search",
        }

    query_tokens = _tokenize(query)

    if not query_tokens:
        return {
            "status": "no_result",
            "executed": True,
            "query": query,
            "message": (
                "The knowledge search query did not "
                "contain searchable terms."
            ),
            "request_type": "knowledge_search",
        }

    # --------------------------------------------------------
    # Search only within the current company.
    # Permissions are checked in Python after retrieval.
    # --------------------------------------------------------

    with _connect() as conn:

        documents = conn.execute(
            """
            SELECT
                document_id,
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
            FROM documents
            WHERE company_id = ?
              AND status = 'active'
            ORDER BY updated_at DESC
            """,
            (
                company_id,
            ),
        ).fetchall()

        results: List[Dict[str, Any]] = []

        for document in documents:

            # ------------------------------------------------
            # Publication / expiry validation
            # ------------------------------------------------

            if not _document_is_current(
                document
            ):
                continue

            # ------------------------------------------------
            # Authorization
            # ------------------------------------------------

            if not _document_is_accessible(
                conn,
                document,
                user_id=user_id,
                user_role=user_role,
                department=department,
            ):
                continue

            chunks = conn.execute(
                """
                SELECT
                    chunk_id,
                    document_id,
                    chunk_index,
                    content,
                    metadata_json,
                    created_at
                FROM document_chunks
                WHERE company_id = ?
                  AND document_id = ?
                ORDER BY chunk_index
                """,
                (
                    company_id,
                    document["document_id"],
                ),
            ).fetchall()

            # ------------------------------------------------
            # Score chunks
            # ------------------------------------------------

            for chunk in chunks:

                content = str(
                    chunk["content"] or ""
                )

                score = _score_document(
                    query_tokens,
                    title=document["title"],
                    category=document["category"],
                    department=document["department"],
                    content=content,
                )

                if score <= 0:
                    continue

                results.append(
                    {
                        "score": score,
                        "document_id": document[
                            "document_id"
                        ],
                        "title": document[
                            "title"
                        ],
                        "filename": document[
                            "filename"
                        ],
                        "category": document[
                            "category"
                        ],
                        "department": document[
                            "department"
                        ],
                        "version": document[
                            "version"
                        ],
                        "chunk_id": chunk[
                            "chunk_id"
                        ],
                        "chunk_index": chunk[
                            "chunk_index"
                        ],
                        "snippet": _make_snippet(
                            content,
                            query_tokens,
                        ),
                        "source": (
                            "Enterprise Knowledge Base"
                        ),
                    }
                )

    # --------------------------------------------------------
    # Rank best matches
    # --------------------------------------------------------

    results.sort(
        key=lambda item: (
            item["score"],
            -int(
                item["chunk_index"]
            ),
        ),
        reverse=True,
    )

    # Remove exact duplicate document/chunk combinations.
    unique_results = []
    seen = set()

    for item in results:

        key = (
            item["document_id"],
            item["chunk_id"],
        )

        if key in seen:
            continue

        seen.add(key)
        unique_results.append(item)

    results = unique_results[:8]

    # --------------------------------------------------------
    # COMPANY UPDATES / IMPORTANT LINKS
    # --------------------------------------------------------

    query_lower = query.lower()

    update_query_terms = {
        "update",
        "updates",
        "latest",
        "recent",
        "announcement",
        "announcements",
        "news",
        "notice",
        "notices",
        "link",
        "links",
    }

    should_search_updates = (
        any(
            term in query_lower
            for term in update_query_terms
        )
        or "company update" in query_lower
        or "company updates" in query_lower
        or "latest company" in query_lower
        or "recent company" in query_lower
    )

    update_results = []

    if should_search_updates:

        try:

            if (
                "latest" in query_lower
                or "recent" in query_lower
                or "updates" in query_lower
                or "announcements" in query_lower
                or "news" in query_lower
            ):

                current_updates = list_updates(
                    company_id, user_id=user_id
                )

                update_results = [
                    {
                        "score": 100 - index,
                        "result_type": "company_update",
                        "update_id": item.get(
                            "update_id"
                        ),
                        "title": item.get(
                            "title"
                        ),
                        "description": item.get(
                            "description"
                        ),
                        "link_url": item.get(
                            "link_url"
                        ),
                        "category": item.get(
                            "category"
                        ),
                        "priority": item.get(
                            "priority"
                        ),
                        "audience": item.get(
                            "audience"
                        ),
                        "posted_by": item.get(
                            "posted_by"
                        ),
                        "published_at": item.get(
                            "published_at"
                        ),
                        "expires_at": item.get(
                            "expires_at"
                        ),
                        "source": (
                            "Company Updates"
                        ),
                    }
                    for index, item in enumerate(
                        current_updates[:8]
                    )
                ]

            else:

                matched_updates = search_updates(
                    company_id,
                    query,
                    limit=8,
                    user_id=user_id,
                )

                update_results = [
                    {
                        **item,
                        "result_type": "company_update",
                        "source": (
                            "Company Updates"
                        ),
                    }
                    for item in matched_updates
                ]

        except Exception:
            update_results = []

    # --------------------------------------------------------
    # Combine documents + company updates
    # --------------------------------------------------------

    combined_results = (
        update_results
        + results
    )

    combined_results = combined_results[:8]

    # --------------------------------------------------------
    # Final response
    # --------------------------------------------------------

    if not combined_results:
        return {
            "status": "no_result",
            "executed": True,
            "request_type": "knowledge_search",
            "query": query,
            "message": (
                "No accessible company knowledge "
                "matched the requested query."
            ),
            "results": [],
            "source": (
                "Enterprise Knowledge Base"
            ),
            "tenant_scoped": True,
            "access_controlled": True,
        }

    return {
        "status": "success",
        "executed": True,
        "request_type": "knowledge_search",
        "query": query,
        "message": (
            f"Found {len(combined_results)} relevant "
            "knowledge or company update result(s)."
        ),
        "results": combined_results,
        "source": (
            "Enterprise Knowledge Base + Company Updates"
        ),
        "tenant_scoped": True,
        "access_controlled": True,
    }


def list_accessible_documents(company_id: str, user_id: str) -> List[Dict[str, Any]]:
    from company.store import authorize_user
    actor = authorize_user(company_id, user_id)
    with _connect() as conn:
        documents = conn.execute("SELECT * FROM documents WHERE company_id=? AND status='active' ORDER BY updated_at DESC", (company_id,)).fetchall()
        result = []
        for document in documents:
            if not _document_is_current(document) or not _document_is_accessible(conn, document, user_id=user_id, user_role=str(actor.get("role") or "employee"), department=str(actor.get("department") or "")):
                continue
            result.append({key: document[key] for key in ("document_id", "title", "filename", "category", "department", "visibility", "version", "updated_at")})
    return result


def read_accessible_document(company_id: str, user_id: str, document_id: int) -> Dict[str, Any]:
    from company.store import authorize_user
    actor = authorize_user(company_id, user_id)
    with _connect() as conn:
        document = conn.execute("SELECT * FROM documents WHERE company_id=? AND document_id=? AND status='active'", (company_id, int(document_id))).fetchone()
        if document is None or not _document_is_current(document) or not _document_is_accessible(conn, document, user_id=user_id, user_role=str(actor.get("role") or "employee"), department=str(actor.get("department") or "")):
            return {"status": "not_found", "message": "The document is unavailable or you do not have permission to view it."}
        path = Path(str(document["storage_path"] or ""))
        title, filename = str(document["title"]), str(document["filename"])
    try:
        data = path.read_bytes()
    except OSError:
        return {"status": "unavailable", "message": "The document file could not be read from company storage."}
    return {"status": "success", "document_id": int(document_id), "title": title, "filename": filename, "data": data}
