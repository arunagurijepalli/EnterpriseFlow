from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from company.store import DB_PATH


def _connect():
    return sqlite3.connect(DB_PATH)


def get_active_policies(
    company_id: str,
    department: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return active policies for a company.

    If department is provided, return policies for that department
    plus company-wide policies.
    """
    conn = _connect()

    try:
        if department:
            rows = conn.execute(
                """
                SELECT
                    policy_id,
                    policy_key,
                    name,
                    description,
                    department,
                    category,
                    priority,
                    risk_level,
                    current_version
                    ,configuration_json,status,updated_at
                FROM policies
                WHERE company_id = ?
                  AND status = 'active'
                  AND (department = ? OR department = '')
                ORDER BY priority DESC, name
                """,
                (company_id, department),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    policy_id,
                    policy_key,
                    name,
                    description,
                    department,
                    category,
                    priority,
                    risk_level,
                    current_version
                    ,configuration_json,status,updated_at
                FROM policies
                WHERE company_id = ?
                  AND status = 'active'
                ORDER BY priority DESC, name
                """,
                (company_id,),
            ).fetchall()

        return [
            {
                "policy_id": row[0],
                "policy_key": row[1],
                "name": row[2],
                "description": row[3],
                "department": row[4],
                "category": row[5],
                "priority": row[6],
                "risk_level": row[7],
                "current_version": row[8],
                "configuration": _json_object(row[9]),
                "status": row[10],
                "updated_at": row[11],
            }
            for row in rows
        ]

    finally:
        conn.close()


def get_policy_rules(
    company_id: str,
    policy_key: str | None = None,
    department: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return active rules from active policies.

    The rule conditions/actions are parsed from JSON into Python objects.
    """
    conn = _connect()

    try:
        query = """
            SELECT
                p.policy_key,
                p.name,
                p.department,
                p.category,
                p.priority,
                p.risk_level,
                r.rule_key,
                r.name,
                r.description,
                r.priority,
                r.conditions_json,
                r.actions_json,
                r.approval_level,
                r.status
            FROM policies p
            JOIN policy_rules r
              ON r.company_id = p.company_id
             AND r.policy_id = p.policy_id
            WHERE p.company_id = ?
              AND p.status = 'active'
              AND r.status = 'active'
        """

        params: list[Any] = [company_id]

        if policy_key:
            query += " AND p.policy_key = ?"
            params.append(policy_key)

        if department:
            query += " AND p.department = ?"
            params.append(department)

        query += """
            ORDER BY
                p.priority DESC,
                r.priority DESC,
                r.rule_key
        """

        rows = conn.execute(query, params).fetchall()

        result = []

        for row in rows:
            try:
                conditions = json.loads(row[10] or "{}")
            except (TypeError, json.JSONDecodeError):
                conditions = {}

            try:
                actions = json.loads(row[11] or "{}")
            except (TypeError, json.JSONDecodeError):
                actions = {}

            result.append(
                {
                    "policy_key": row[0],
                    "policy_name": row[1],
                    "department": row[2],
                    "category": row[3],
                    "policy_priority": row[4],
                    "risk_level": row[5],
                    "rule_key": row[6],
                    "rule_name": row[7],
                    "description": row[8],
                    "priority": row[9],
                    "conditions": conditions,
                    "actions": actions,
                    "approval_level": row[12] or "",
                    "status": row[13],
                }
            )

        return result

    finally:
        conn.close()


def get_policy_value(
    company_id: str,
    rule_key: str,
    default: Any = None,
) -> Any:
    """
    Get a single configured value from an active policy rule.

    Example:
        get_policy_value(
            "demo_company",
            "annual_leave_days"
        )
        -> 20
    """
    rules = get_policy_rules(company_id)

    for rule in rules:
        if rule["rule_key"] != rule_key:
            continue

        actions = rule.get("actions", {})

        if rule_key in actions:
            return actions[rule_key]

    return default


def get_policy_context(
    company_id: str,
    department: str | None = None,
) -> dict[str, Any]:
    """
    Build a structured policy context for the workflow.

    This is configuration data from the database, not an LLM decision.
    """
    policies = get_active_policies(
        company_id=company_id,
        department=department,
    )

    rules = get_policy_rules(
        company_id=company_id,
        department=department,
    )

    values: dict[str, Any] = {}

    for rule in rules:
        values.update(rule.get("actions", {}))

    return {
        "company_id": company_id,
        "department": department,
        "policies": policies,
        "rules": rules,
        "values": values,
    }


def _json_object(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def save_policy_configuration(*, company_id: str, user_id: str, policy_key: str,
                              name: str, department: str, category: str,
                              configuration: dict[str, Any]) -> dict[str, Any]:
    """Version a business policy and synchronize its executable values."""
    from company.store import authorize_user
    authorize_user(company_id, user_id, allowed_roles=["company_admin"])
    key = str(policy_key or "").strip().lower()
    name = str(name or "").strip()
    department = str(department or "").strip()
    if key not in {"leave_policy", "laptop_purchase_policy", "purchase_approval_policy", "finance_budget_policy"}:
        raise ValueError("Choose a supported workflow policy.")
    if not name or not isinstance(configuration, dict) or not configuration:
        raise ValueError("Policy name and configuration are required.")
    
    if key == "leave_policy":
        try:
            days = int(configuration.get("annual_leave_days", -1))
        except (TypeError, ValueError) as exc:
            raise ValueError("Annual leave days must be a whole number.") from exc
        if days < 0:
            raise ValueError("Annual leave days cannot be negative.")

        holidays = configuration.get("holidays", [])
        if not isinstance(holidays, list):
            raise ValueError("Holidays must be a list of dates.")

        from datetime import date

        normalized_holidays = []
        for item in holidays:
            value = item.get("date") if isinstance(item, dict) else item
            try:
                normalized_holidays.append(
                    date.fromisoformat(str(value).strip()).isoformat()
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid holiday date: {value}. Use YYYY-MM-DD."
                ) from exc

        leave_types = configuration.get("leave_types", ["Annual Leave"])
        if not isinstance(leave_types, list) or not all(
            isinstance(item, str) and item.strip() for item in leave_types
        ):
            raise ValueError("Leave types must be a list of non-empty names.")

        configuration = {
            "annual_leave_days": days,
            "manager_approval_required": bool(
                configuration.get("manager_approval_required", True)
            ),
            "count_weekends": bool(configuration.get("count_weekends", False)),
            "holidays": sorted(set(normalized_holidays)),
            "leave_types": list(dict.fromkeys(item.strip() for item in leave_types)),
        }
    elif key == "laptop_purchase_policy":
        limit = float(configuration.get("laptop_budget_inr", -1))
        if limit < 0:
            raise ValueError("Laptop budget cannot be negative.")
        configuration = {"laptop_budget_inr": limit}
    elif key == "purchase_approval_policy":
        threshold = float(configuration.get("purchase_above_inr", -1))
        if threshold < 0:
            raise ValueError("Purchase approval threshold cannot be negative.")
        configuration = {"purchase_above_inr": threshold}
    elif key == "finance_budget_policy":
        budget = float(configuration.get("finance_available_budget_inr", -1))
        currency = str(configuration.get("finance_currency") or "").strip().upper()
        if budget < 0 or len(currency) != 3:
            raise ValueError("Provide a valid Finance budget and three-letter currency.")
        configuration = {"finance_available_budget_inr": budget, "finance_currency": currency}

    now = datetime.now(timezone.utc).isoformat()
    serialized = json.dumps(configuration, ensure_ascii=False, sort_keys=True)
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        company_row = conn.execute("SELECT context_json FROM companies WHERE company_id=?", (company_id,)).fetchone()
        if company_row is None:
            raise ValueError("Company tenant was not found.")
        context = _json_object(company_row["context_json"])
        policies = context.get("policies") if isinstance(context.get("policies"), dict) else {}
        approval_rules = context.get("approval_rules") if isinstance(context.get("approval_rules"), dict) else {}
        if key == "leave_policy":
            policies["leave"] = configuration
        elif key == "laptop_purchase_policy":
            policies["laptop_budget_inr"] = configuration["laptop_budget_inr"]
        elif key == "purchase_approval_policy":
            approval_rules["purchase_above_inr"] = configuration["purchase_above_inr"]
        elif key == "finance_budget_policy":
            policies.update(configuration)
        context["policies"] = policies
        context["approval_rules"] = approval_rules
        conn.execute("UPDATE companies SET context_json=?,updated_at=? WHERE company_id=?", (json.dumps(context, ensure_ascii=False), now, company_id))

        existing = conn.execute("SELECT policy_id,current_version,configuration_json FROM policies WHERE company_id=? AND policy_key=?", (company_id, key)).fetchone()
        if existing:
            policy_id = int(existing["policy_id"])
            version = int(existing["current_version"] or 0) + 1
            conn.execute("UPDATE policies SET name=?,description=?,department=?,category=?,status='active',current_version=?,configuration_json=?,updated_at=? WHERE company_id=? AND policy_id=?", (name, f"Versioned executable policy: {name}", department, category, version, serialized, now, company_id, policy_id))
        else:
            version = 1
            cur = conn.execute("INSERT INTO policies(company_id,policy_key,name,description,department,category,status,current_version,created_by,configuration_json,created_at,updated_at) VALUES(?,?,?,?,?,?,'active',?,?,?, ?,?)", (company_id, key, name, f"Versioned executable policy: {name}", department, category, version, user_id, serialized, now, now))
            policy_id = int(cur.lastrowid)
        conn.execute("INSERT INTO policy_versions(company_id,policy_id,version_number,summary,created_by,created_at) VALUES(?,?,?,?,?,?)", (company_id, policy_id, version, serialized, user_id, now))
        conn.execute("INSERT INTO audit_logs(company_id,user_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?)", (company_id, user_id, "policy_version_saved", "policy", str(policy_id), json.dumps({"policy_key": key, "version": version}), now))
    return {"status": "success", "policy_id": policy_id, "policy_key": key, "version": version, "configuration": configuration, "message": f"{name} saved as version {version}. New workflows will use these values."}
