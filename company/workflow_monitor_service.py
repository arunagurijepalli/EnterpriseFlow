"""Admin-only tenant-scoped workflow monitor queries."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from company.store import DB_PATH, authorize_user, initialize_company_store


def list_company_workflows(company_id: str, admin_user_id: str, *, search: str = "",
                           status: str = "", limit: int = 250) -> list[dict[str, Any]]:
    authorize_user(company_id, admin_user_id, allowed_roles=["company_admin"])
    initialize_company_store()
    query = """SELECT w.workflow_id,w.user_id,u.name AS employee,w.request_text,w.request_category,
                     w.intent,w.status,w.decision,w.assigned_agents_json,w.selected_tools_json,
                     w.created_at,w.updated_at
              FROM workflow_requests w LEFT JOIN company_users u
                ON u.company_id=w.company_id AND u.user_id=w.user_id
              WHERE w.company_id=?"""
    params: list[Any] = [company_id]
    if status and status != "All":
        query += " AND lower(w.status)=lower(?)"
        params.append(status)
    if search.strip():
        pattern = f"%{search.strip()}%"
        query += " AND (w.workflow_id LIKE ? OR w.request_text LIKE ? OR u.name LIKE ?)"
        params.extend([pattern, pattern, pattern])
    query += " ORDER BY w.updated_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 1000)))
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    for row in rows:
        for source, target, default in (("decision", "decision", {}), ("assigned_agents_json", "agents", []), ("selected_tools_json", "tools", [])):
            try:
                row[target] = json.loads(row.pop(source) or "null") if source != "decision" else json.loads(row.get(source) or "{}")
            except (TypeError, json.JSONDecodeError):
                row[target] = default
        if "decision" in row and not isinstance(row["decision"], dict):
            row["decision"] = {}
    return rows


def get_company_workflow_details(company_id: str, admin_user_id: str, workflow_id: str) -> dict[str, Any]:
    authorize_user(company_id, admin_user_id, allowed_roles=["company_admin"])
    initialize_company_store()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM workflow_requests WHERE company_id=? AND workflow_id=?", (company_id, workflow_id)).fetchone()
        if row is None:
            return {}
        request = dict(row)
        for source, target, default in (("decision", "decision", {}), ("assigned_agents_json", "agents", []), ("selected_tools_json", "tools", []), ("context_json", "context", {})):
            try:
                request[target] = json.loads(request.get(source) or "{}" if source in {"decision", "context_json"} else request.get(source) or "[]")
            except (TypeError, json.JSONDecodeError):
                request[target] = default
        executions = [dict(item) for item in conn.execute("SELECT execution_id,stage,agent_key,tool_key,input_json,output_json,status,created_at FROM workflow_executions WHERE company_id=? AND workflow_id=? ORDER BY execution_id", (company_id, workflow_id)).fetchall()]
        approvals = [dict(item) for item in conn.execute("SELECT approval_id,approval_type,status,reason,requested_at,decided_at,approver_user_id,metadata_json FROM approvals WHERE company_id=? AND workflow_id=? ORDER BY requested_at", (company_id, workflow_id)).fetchall()]
    for item in executions:
        for source, target in (("input_json", "input"), ("output_json", "output")):
            try:
                item[target] = json.loads(item.pop(source) or "{}")
            except (TypeError, json.JSONDecodeError):
                item[target] = {}
    for item in approvals:
        try:
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["metadata"] = {}
    request["executions"] = executions
    request["approvals"] = approvals
    return request
