"""Tenant-safe employee self-registration using the existing company database."""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone

from company.store import DB_PATH, initialize_company_store
from company.auth import hash_password

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def register_employee(
    name: str,
    email: str,
    password: str,
    department: str = "",
    phone: str = "",
    designation: str = "",
    employee_id: str = "",
) -> dict:
    """Create an employee login and its directory profile atomically."""
    name = str(name or "").strip()
    email = str(email or "").strip().lower()
    password = str(password or "")
    department = str(department or "").strip()
    phone = str(phone or "").strip()
    designation = str(designation or "").strip()
    requested_employee_id = str(employee_id or "").strip()

    if len(name) < 2:
        raise ValueError("Enter your full name.")
    if not EMAIL_RE.fullmatch(email):
        raise ValueError("Enter a valid company work email address.")
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")
    if requested_employee_id and (len(requested_employee_id) > 64 or not re.fullmatch(r"[A-Za-z0-9_-]+", requested_employee_id)):
        raise ValueError("Enter a valid employee ID or leave it blank.")

    domain = email.rsplit("@", 1)[1].lower()
    initialize_company_store()
    salt, digest = hash_password(password)
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        companies = conn.execute(
            "SELECT company_id, domain, context_json FROM companies WHERE lower(trim(domain)) = ?",
            (domain,),
        ).fetchall()
        if len(companies) != 1:
            raise ValueError("Self-registration is unavailable for this email domain. Ask your company administrator for an invitation or approved domain.")
        company = companies[0]
        company_id = str(company["company_id"])
        if conn.execute("SELECT 1 FROM company_users WHERE lower(trim(email))=?", (email,)).fetchone():
            raise ValueError("An account with this email already exists. Please sign in instead.")
        if department and department not in json.loads(company["context_json"] or "{}").get("departments", []):
            raise ValueError("Select a valid department for your company.")

        if requested_employee_id:
            if conn.execute("SELECT 1 FROM company_users WHERE company_id=? AND employee_id=?", (company_id, requested_employee_id)).fetchone() or conn.execute("SELECT 1 FROM employee_profiles WHERE company_id=? AND employee_id=?", (company_id, requested_employee_id)).fetchone():
                raise ValueError("This employee ID is already in use.")
            employee_id = requested_employee_id
        else:
            existing_ids = []
            for table in ("company_users", "employee_profiles"):
                existing_ids.extend(conn.execute(f"SELECT employee_id FROM {table} WHERE company_id=? AND employee_id LIKE 'EMP%'", (company_id,)).fetchall())
            nums = [int(str(r[0])[3:]) for r in existing_ids if str(r[0] or "")[3:].isdigit()]
            employee_id = f"EMP{max(nums, default=0)+1:04d}"

        user_id = "usr_" + uuid.uuid4().hex
        conn.execute("""INSERT INTO company_users
            (user_id, employee_id, company_id, name, email, role, department, status,
             password_hash, password_salt, failed_attempts, locked_until, last_login_at,
             created_at, updated_at, account_status)
            VALUES (?, ?, ?, ?, ?, 'employee', ?, 'active', ?, ?, 0, '', '', ?, ?, 'active')""",
            (user_id, employee_id, company_id, name, email, department, digest, salt, now, now))
        conn.execute("""INSERT INTO employee_profiles
            (employee_id, company_id, user_id, full_name, email, phone, department, job_title,
             role_name, manager_employee_id, joining_date, employment_status, location, date_of_birth,
             leave_entitlement_days, leave_balance_days, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'employee', '', ?, 'active', '', '', 20, 20, ?, ?)""",
            (employee_id, company_id, user_id, name, email, phone, department, designation, now[:10], now, now))
        conn.commit()
        return {"user_id": user_id, "employee_id": employee_id, "company_id": company_id, "name": name, "email": email, "phone": phone, "department": department, "designation": designation, "status": "active"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
