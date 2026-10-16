"""Tenant-visible runtime state for the built-in department agents."""
from __future__ import annotations

import importlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from company.store import DB_PATH, authorize_user, initialize_company_store

BUILT_IN_AGENTS = (
    ("hr", "HR Agent", "HR", "agents.hr_agent", "run_hr_agent"),
    ("it", "IT Support Agent", "IT", "agents.it_agent", "run_it_agent"),
    ("finance", "Finance Agent", "Finance", "agents.finance_agent", "run_finance_agent"),
    ("procurement", "Procurement Agent", "Procurement", "agents.procurement_agent", "run_procurement_agent"),
    ("knowledge", "Knowledge Agent", "Knowledge", "agents.knowledge_agent", "run_knowledge_agent"),
)


def list_agent_runtime_status(company_id: str, user_id: str) -> list[dict[str, Any]]:
    authorize_user(company_id, user_id)
    initialize_company_store()
    now = datetime.now(timezone.utc).isoformat()
    runtime = []
    for key, name, department, module_name, entrypoint in BUILT_IN_AGENTS:
        try:
            module = importlib.import_module(module_name)
            available = callable(getattr(module, entrypoint, None))
        except Exception:
            available = False
        status = "active" if available else "offline"
        runtime.append({"key": key, "name": name, "department": department, "status": status, "module": module_name})
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                """INSERT INTO company_agents(company_id,agent_key,name,description,agent_type,status,configuration_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(company_id,agent_key) DO UPDATE SET name=excluded.name,status=excluded.status,updated_at=excluded.updated_at""",
                (company_id, key, name, f"Runtime-backed {department} workflow agent", "specialist", status, json.dumps({"module": module_name, "entrypoint": entrypoint}), now, now),
            )
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        records = conn.execute("SELECT agent_key,status,updated_at FROM company_agents WHERE company_id=?", (company_id,)).fetchall()
        workflow_rows = conn.execute("SELECT assigned_agents_json,status,updated_at FROM workflow_requests WHERE company_id=?", (company_id,)).fetchall()
    registry = {str(row["agent_key"]): dict(row) for row in records}
    active_counts = {key: 0 for key, *_ in BUILT_IN_AGENTS}
    last_activity = {key: "" for key, *_ in BUILT_IN_AGENTS}
    for row in workflow_rows:
        try:
            assigned = json.loads(row["assigned_agents_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            assigned = []
        status_value = str(row["status"] or "").lower()
        for key, name, *_ in BUILT_IN_AGENTS:
            if name in assigned:
                if status_value in {"started", "pending_approval", "awaiting_confirmation", "in_progress"}:
                    active_counts[key] += 1
                stamp = str(row["updated_at"] or "")
                if stamp > last_activity[key]:
                    last_activity[key] = stamp
    for item in runtime:
        item["status"] = str(registry.get(item["key"], {}).get("status") or item["status"])
        item["active_workflows"] = active_counts[item["key"]]
        item["last_activity"] = last_activity[item["key"]]
    return runtime
