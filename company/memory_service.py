from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from company.store import DB_PATH, initialize_company_store


# ============================================================
# HELPERS
# ============================================================

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    initialize_company_store()

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _json_dump(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
    )


def _json_load(value: Any, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default


# ============================================================
# CONVERSATION MEMORY
# ============================================================

def create_conversation(
    company_id: str,
    user_id: str,
    title: str = "",
) -> Dict[str, Any]:

    initialize_company_store()

    now = _utc_now()

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO conversations
            (
                company_id,
                user_id,
                title,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
            (
                company_id,
                user_id,
                title,
                now,
                now,
            ),
        )

        conversation_id = cursor.lastrowid

    return get_conversation(
        company_id,
        conversation_id,
    )

def get_conversation(
    company_id: str,
    conversation_id: int,
) -> Dict[str, Any]:

    initialize_company_store()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                conversation_id,
                company_id,
                user_id,
                title,
                status,
                created_at,
                updated_at
            FROM conversations
            WHERE company_id = ?
              AND conversation_id = ?
            """,
            (
                company_id,
                int(conversation_id),
            ),
        ).fetchone()

    if not row:
        return {}

    return dict(row)


def save_conversation_message(
    company_id: str,
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    message_id = None
    now = _utc_now()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversation_messages
            (
                message_id,
                company_id,
                conversation_id,
                user_id,
                role,
                content,
                metadata_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                company_id,
                conversation_id,
                user_id,
                role,
                content,
                _json_dump(metadata or {}),
                now,
            ),
        )

        conn.execute(
            """
            UPDATE conversations
            SET updated_at = ?
            WHERE company_id = ?
              AND conversation_id = ?
            """,
            (
                now,
                company_id,
                conversation_id,
            ),
        )

        message_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "created_at": now,
    }


# ============================================================
# SHORT-TERM MEMORY
# ============================================================

def set_short_term_memory(
    company_id: str,
    user_id: str,
    memory_key: str,
    memory_value: Any,
    conversation_id: str = "",
    workflow_id: str = "",
    ttl_minutes: Optional[int] = 120,
) -> Dict[str, Any]:

    now = _utc_now()

    expires_at = None

    if ttl_minutes is not None:
        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(minutes=int(ttl_minutes))
        ).isoformat()

    with _connect() as conn:

        existing = conn.execute(
            """
            SELECT memory_id
            FROM short_term_memory
            WHERE company_id = ?
              AND user_id = ?
              AND memory_key = ?
              AND COALESCE(conversation_id, '') = ?
            ORDER BY memory_id DESC
            LIMIT 1
            """,
            (
                company_id,
                user_id,
                memory_key,
                conversation_id or "",
            ),
        ).fetchone()

        if existing:

            conn.execute(
                """
                UPDATE short_term_memory
                SET memory_value_json = ?,
                    workflow_id = ?,
                    expires_at = ?,
                    updated_at = ?
                WHERE memory_id = ?
                """,
                (
                    _json_dump(memory_value),
                    workflow_id,
                    expires_at,
                    now,
                    existing["memory_id"],
                ),
            )

            memory_id = existing["memory_id"]

        else:

            memory_id = None

            conn.execute(
                """
                INSERT INTO short_term_memory
                (
                    memory_id,
                    company_id,
                    user_id,
                    conversation_id,
                    workflow_id,
                    memory_key,
                    memory_value_json,
                    expires_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    company_id,
                    user_id,
                    conversation_id,
                    workflow_id,
                    memory_key,
                    _json_dump(memory_value),
                    expires_at,
                    now,
                    now,
                ),
            )

            memory_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return {
        "memory_id": memory_id,
        "memory_key": memory_key,
        "memory_value": memory_value,
        "expires_at": expires_at,
    }


def get_short_term_memory(
    company_id: str,
    user_id: str,
    conversation_id: str = "",
) -> Dict[str, Any]:

    now = _utc_now()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM short_term_memory
            WHERE company_id = ?
              AND user_id = ?
              AND COALESCE(conversation_id, '') = ?
              AND (
                    expires_at IS NULL
                    OR expires_at > ?
                  )
            ORDER BY updated_at DESC
            """,
            (
                company_id,
                user_id,
                conversation_id or "",
                now,
            ),
        ).fetchall()

    result = {}

    for row in rows:
        result[row["memory_key"]] = _json_load(
            row["memory_value_json"],
            None,
        )

    return result


def clear_expired_short_term_memory() -> int:

    now = _utc_now()

    with _connect() as conn:
        cursor = conn.execute(
            """
            DELETE FROM short_term_memory
            WHERE expires_at IS NOT NULL
              AND expires_at <= ?
            """,
            (now,),
        )

    return cursor.rowcount


# ============================================================
# LONG-TERM MEMORY
# ============================================================

def save_long_term_memory(
    company_id: str,
    user_id: str,
    memory_type: str,
    memory_key: str,
    content: str,
    source_type: str = "",
    source_id: str = "",
    confidence: float = 1.0,
    metadata: Optional[Dict[str, Any]] = None,
    status: str = "active",
) -> Dict[str, Any]:

    memory_id = None
    now = _utc_now()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO long_term_memory
            (
                memory_id,
                company_id,
                user_id,
                memory_type,
                memory_key,
                content,
                source_type,
                source_id,
                confidence,
                metadata_json,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                company_id,
                user_id,
                memory_type,
                memory_key,
                content,
                source_type,
                source_id,
                float(confidence),
                _json_dump(metadata or {}),
                status,
                now,
                now,
            ),
        )

        memory_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return {
        "memory_id": memory_id,
        "memory_type": memory_type,
        "memory_key": memory_key,
        "content": content,
        "confidence": confidence,
        "status": status,
    }


def search_long_term_memory(
    company_id: str,
    query: str = "",
    user_id: Optional[str] = None,
    memory_type: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:

    sql = """
        SELECT *
        FROM long_term_memory
        WHERE company_id = ?
          AND status = 'active'
    """

    params: List[Any] = [company_id]

    if user_id:
        sql += " AND (user_id = ? OR user_id = '')"
        params.append(user_id)

    if memory_type:
        sql += " AND memory_type = ?"
        params.append(memory_type)

    if query:
        sql += """
            AND (
                lower(memory_key) LIKE lower(?)
                OR lower(content) LIKE lower(?)
            )
        """
        pattern = f"%{query}%"
        params.extend(
            [
                pattern,
                pattern,
            ]
        )

    sql += """
        ORDER BY confidence DESC, updated_at DESC
        LIMIT ?
    """

    params.append(int(limit))

    with _connect() as conn:
        rows = conn.execute(
            sql,
            tuple(params),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# WORKFLOW PERSISTENCE
# ============================================================

def save_workflow_request(
    workflow_id: str,
    company_id: str,
    user_id: str,
    request_text: str,
    request_category: str = "",
    intent: str = "",
    status: str = "started",
    decision: Optional[Dict[str, Any]] = None,
    assigned_agents: Optional[List[str]] = None,
    selected_tools: Optional[List[str]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    now = _utc_now()

    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO workflow_requests
            (
                workflow_id,
                company_id,
                user_id,
                request_text,
                request_category,
                intent,
                status,
                decision,
                assigned_agents_json,
                selected_tools_json,
                context_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                company_id,
                user_id,
                request_text,
                request_category,
                intent,
                status,
                _json_dump(decision or {}),
                _json_dump(assigned_agents or []),
                _json_dump(selected_tools or []),
                _json_dump(context or {}),
                now,
                now,
            ),
        )

    return get_workflow_request(
        company_id,
        workflow_id,
    )


def get_workflow_request(
    company_id: str,
    workflow_id: str,
) -> Dict[str, Any]:

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM workflow_requests
            WHERE company_id = ?
              AND workflow_id = ?
            """,
            (
                company_id,
                workflow_id,
            ),
        ).fetchone()

    if not row:
        return {}

    result = dict(row)

    result["decision"] = _json_load(
        result.get("decision"),
        {},
    )

    result["assigned_agents"] = _json_load(
        result.get("assigned_agents_json"),
        [],
    )

    result["selected_tools"] = _json_load(
        result.get("selected_tools_json"),
        [],
    )

    result["context"] = _json_load(
        result.get("context_json"),
        {},
    )

    return result


def update_workflow_status(
    company_id: str,
    workflow_id: str,
    status: str,
    decision: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    now = _utc_now()

    with _connect() as conn:
        conn.execute(
            """
            UPDATE workflow_requests
            SET status = ?,
                decision = ?,
                updated_at = ?
            WHERE company_id = ?
              AND workflow_id = ?
            """,
            (
                status,
                _json_dump(decision or {}),
                now,
                company_id,
                workflow_id,
            ),
        )

    return get_workflow_request(
        company_id,
        workflow_id,
    )


def save_workflow_execution(
    company_id: str,
    workflow_id: str,
    stage: str,
    agent_key: str = "",
    tool_key: str = "",
    input_data: Optional[Dict[str, Any]] = None,
    output_data: Optional[Any] = None,
    status: str = "completed",
) -> Dict[str, Any]:

    execution_id = None
    now = _utc_now()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO workflow_executions
            (
                execution_id,
                company_id,
                workflow_id,
                stage,
                agent_key,
                tool_key,
                input_json,
                output_json,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id,
                company_id,
                workflow_id,
                stage,
                agent_key,
                tool_key,
                _json_dump(input_data or {}),
                _json_dump(output_data),
                status,
                now,
            ),
        )

        execution_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return {
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "stage": stage,
        "status": status,
        "created_at": now,
    }


def get_my_workflow_details(company_id: str, user_id: str, workflow_id: str) -> Dict[str, Any]:
    """Return a workflow's persisted detail only to its owning employee."""
    from company.store import authorize_user
    authorize_user(company_id, user_id)
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM workflow_requests WHERE company_id=? AND user_id=? AND workflow_id=?",
            (company_id, user_id, workflow_id),
        ).fetchone()
        if row is None:
            return {}
        request = dict(row)
        request["decision"] = _json_load(request.get("decision"), {})
        request["assigned_agents"] = _json_load(request.get("assigned_agents_json"), [])
        request["selected_tools"] = _json_load(request.get("selected_tools_json"), [])
        request["context"] = _json_load(request.get("context_json"), {})
        executions = conn.execute(
            "SELECT stage,agent_key,tool_key,status,created_at,output_json FROM workflow_executions WHERE company_id=? AND workflow_id=? ORDER BY created_at,execution_id",
            (company_id, workflow_id),
        ).fetchall()
        approvals = conn.execute(
            "SELECT approval_id,approval_type,status,reason,requested_at,decided_at,approver_user_id,metadata_json FROM approvals WHERE company_id=? AND workflow_id=? ORDER BY requested_at",
            (company_id, workflow_id),
        ).fetchall()
    request["executions"] = []
    for execution in executions:
        item = dict(execution)
        item["output"] = _json_load(item.pop("output_json"), {})
        request["executions"].append(item)
    request["approvals"] = []
    for approval in approvals:
        item = dict(approval)
        item["metadata"] = _json_load(item.pop("metadata_json"), {})
        request["approvals"].append(item)
    return request





# ============================================================
# PERSISTENT CHAT HISTORY
# ============================================================

def list_user_conversations(company_id: str, user_id: str) -> List[Dict[str, Any]]:
    """List only the signed-in user's conversations in this company."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT conversation_id, title, status, created_at, updated_at
            FROM conversations
            WHERE company_id = ? AND user_id = ?
              AND status != 'deleted'
            ORDER BY updated_at DESC, conversation_id DESC
            """,
            (company_id, user_id),
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_conversation_messages(
    company_id: str, user_id: str, conversation_id: int
) -> List[Dict[str, Any]]:
    """Load messages only when the conversation belongs to this user."""
    with _connect() as conn:
        owned = conn.execute(
            """
            SELECT 1 FROM conversations
            WHERE company_id = ? AND user_id = ? AND conversation_id = ?
              AND status != 'deleted'
            """,
            (company_id, user_id, int(conversation_id)),
        ).fetchone()
        if not owned:
            return []

        rows = conn.execute(
            """
            SELECT role, content, metadata_json, created_at
            FROM conversation_messages
            WHERE company_id = ? AND user_id = ? AND conversation_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (company_id, user_id, int(conversation_id)),
        ).fetchall()

    messages = []
    for row in rows:
        item = dict(row)
        metadata = _json_load(item.pop("metadata_json", "{}"), {})
        item["result"] = None
        item["time"] = item.get("created_at", "")
        item["metadata"] = metadata
        messages.append(item)
    return messages


def delete_user_conversation(
    company_id: str, user_id: str, conversation_id: int
) -> bool:
    """Soft-delete only the signed-in user's conversation."""
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE conversations
            SET status = 'deleted', updated_at = ?
            WHERE company_id = ? AND user_id = ? AND conversation_id = ?
            """,
            (_utc_now(), company_id, user_id, int(conversation_id)),
        )
        return cursor.rowcount > 0
