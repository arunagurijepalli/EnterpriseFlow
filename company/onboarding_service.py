"""Self-service onboarding for a new company tenant and its first admin."""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone

from company.auth import set_password
from company.store import DB_PATH, add_company_user, get_company, register_company


def create_company_workspace(*, company_id: str = "", company_name: str, admin_name: str,
                             admin_email: str, password: str, company_domain: str = "",
                             industry: str = "", location: str = "", timezone_name: str = "") -> dict[str, str]:
    company_id = str(company_id or "").strip().lower()
    company_name = str(company_name or "").strip()
    admin_name = str(admin_name or "").strip()
    admin_email = str(admin_email or "").strip().lower()
    if not company_name or not admin_name:
        raise ValueError("Company name and administrator name are required.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", admin_email):
        raise ValueError("Enter a valid work email address.")
    if len(str(password or "")) < 8:
        raise ValueError("Password must contain at least 8 characters.")
    if not company_id:
        base = re.sub(r"[^a-z0-9]+", "-", company_name.casefold()).strip("-")[:32] or "company"
        company_id = f"{base}-{uuid.uuid4().hex[:8]}"
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9_-]{1,48}[a-z0-9])?", company_id):
        raise ValueError("Generated workspace ID is invalid. Please try again.")
    if get_company(company_id):
        raise ValueError("That workspace ID is already in use.")

    user_id = f"admin_{uuid.uuid4().hex[:16]}"
    company_created = False
    try:
        register_company(
            company_id,
            company_name,
            domain=(str(company_domain or "").strip().lower() or admin_email.rsplit("@", 1)[1]),
            context={"departments": ["HR", "IT", "Finance", "Procurement", "Recruitment", "Knowledge"],
                     "organization_metadata": {"industry": str(industry).strip(), "location": str(location).strip(),
                                               "timezone": str(timezone_name).strip()}},
        )
        company_created = True
        add_company_user(user_id, company_id, admin_name, admin_email, role="company_admin")
        set_password(user_id, password)
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO audit_logs(company_id,user_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (company_id, user_id, "company_workspace_created", "company", company_id,
                 '{"initial_role":"company_admin"}', now),
            )
        return {"company_id": company_id, "user_id": user_id, "email": admin_email,
                "domain": str(company_domain or "").strip().lower() or admin_email.rsplit("@", 1)[1],
                "industry": str(industry).strip(), "location": str(location).strip(),
                "timezone": str(timezone_name).strip()}
    except Exception:
        if company_created:
            with sqlite3.connect(str(DB_PATH)) as conn:
                conn.execute("DELETE FROM companies WHERE company_id=?", (company_id,))
        raise
