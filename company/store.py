from __future__ import annotations

from contextlib import contextmanager

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from company.enterprise_schema import initialize_enterprise_schema
from company.employee_schema import initialize_employee_schema
from dotenv import load_dotenv

# Load this project's .env before deriving DB_PATH. Previously store.py could
# be imported by ui.app before core.llm loaded dotenv, so COMPANY_DB_PATH in
# .env was silently ignored and a different working directory could select a
# different database. Relative database paths are now anchored to BASE_DIR.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)
DATA_DIR = BASE_DIR / "data"
_raw_db_path = os.getenv("COMPANY_DB_PATH", str(DATA_DIR / "company.db")).strip()
_configured_db_path = Path(_raw_db_path).expanduser()
if not _configured_db_path.is_absolute():
    _configured_db_path = BASE_DIR / _configured_db_path
DB_PATH = _configured_db_path.resolve()

DEFAULT_ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "employee": ["self_service"],
    "hr_admin": ["self_service", "HR"],
    "it_admin": ["self_service", "IT"],
    "finance_admin": ["self_service", "Finance"],
    "procurement_admin": ["self_service", "Procurement"],
    "recruitment_admin": ["self_service", "Recruitment"],
    "company_admin": [
        "self_service",
        "company_configuration",
        "HR",
        "IT",
        "Finance",
        "Procurement",
        "Recruitment",
    ],
}

DEFAULT_COMPANY_CONTEXT: Dict[str, Any] = {
    "departments": [
        "HR",
        "IT",
        "Finance",
        "Procurement",
        "Recruitment",
    ],
    "policies": {},
    "approval_rules": {},
    "locations": [],
    "holidays": [],
    "benefits": {},
    "tool_overrides": {},
    "organization_metadata": {},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect():
    """Yield a configured connection and always commit/close it."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_user_auth_columns(conn: sqlite3.Connection) -> None:
    """Migrate older company databases without destroying existing tenant data."""

    existing = {
        str(row[1])
        for row in conn.execute(
            "PRAGMA table_info(company_users)"
        ).fetchall()
    }

    columns = {
        "employee_id": "TEXT DEFAULT ''",
        "password_hash": "TEXT DEFAULT ''",
        "password_salt": "TEXT DEFAULT ''",
        "failed_attempts": "INTEGER NOT NULL DEFAULT 0",
        "locked_until": "TEXT DEFAULT ''",
        "last_login_at": "TEXT DEFAULT ''",
        "account_status": "TEXT NOT NULL DEFAULT 'active'",
    }

    for name, definition in columns.items():
        if name not in existing:
            conn.execute(
                f"ALTER TABLE company_users ADD COLUMN {name} {definition}"
            )


def initialize_company_store() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                company_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                domain TEXT DEFAULT '',
                context_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS company_users (
                user_id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT DEFAULT '',
                role TEXT NOT NULL DEFAULT 'employee',
                department TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                password_hash TEXT DEFAULT '',
                password_salt TEXT DEFAULT '',
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT DEFAULT '',
                last_login_at TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(company_id) REFERENCES companies(company_id)
                    ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_company_users_company "
            "ON company_users(company_id)"
        )

        _ensure_user_auth_columns(conn)

        # Enforce case-insensitive email uniqueness when legacy data permits it.
        # Existing duplicate records, if any, are preserved rather than deleted;
        # registration_service still rejects duplicate addresses transactionally.
        duplicate_email = conn.execute(
            """SELECT 1 FROM company_users
               WHERE trim(COALESCE(email, '')) <> ''
               GROUP BY lower(trim(email)) HAVING COUNT(*) > 1 LIMIT 1"""
        ).fetchone()
        if not duplicate_email:
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_company_users_email_normalized
                   ON company_users(lower(trim(email)))
                   WHERE trim(COALESCE(email, '')) <> ''"""
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS company_role_permissions (
                company_id TEXT NOT NULL,
                role TEXT NOT NULL,
                permissions_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (company_id, role),
                FOREIGN KEY(company_id) REFERENCES companies(company_id)
                    ON DELETE CASCADE
            )
            """
        )

        company_rows = conn.execute(
            "SELECT company_id FROM companies"
        ).fetchall()

        now = _utc_now()

        for company_row in company_rows:
            company_id = str(company_row["company_id"])

            for role, permissions in DEFAULT_ROLE_PERMISSIONS.items():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO company_role_permissions
                    (company_id, role, permissions_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        company_id,
                        role,
                        json.dumps(permissions),
                        now,
                    ),
                )

        initialize_enterprise_schema(conn)

        # Employee Master + Employee Service History tables
        initialize_employee_schema(conn)


def _merge_context(
    base: Dict[str, Any],
    incoming: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    result = dict(base)

    if not incoming:
        return result

    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            merged = dict(result[key])
            merged.update(value)
            result[key] = merged
        else:
            result[key] = value

    return result


def register_company(
    company_id: str,
    name: str,
    domain: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    company_id = str(company_id).strip()
    name = str(name).strip()

    if not company_id or not name:
        raise ValueError("company_id and company name are required")

    now = _utc_now()

    company_context = _merge_context(
        DEFAULT_COMPANY_CONTEXT,
        context,
    )

    with _connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO companies
                (company_id, name, domain, context_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    name,
                    str(domain or "").strip(),
                    json.dumps(
                        company_context,
                        ensure_ascii=False,
                        default=str,
                    ),
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Company '{company_id}' already exists"
            ) from exc

        # Keep organization units normalized while retaining the existing
        # context shape for backward-compatible workflow consumers.
        departments = company_context.get("departments", [])
        for item in departments if isinstance(departments, list) else []:
            department = str(item or "").strip()
            if department:
                conn.execute(
                    "INSERT OR IGNORE INTO company_departments(company_id,name,description,status,created_at,updated_at) VALUES(?,?,?,'active',?,?)",
                    (company_id, department, "", now, now),
                )

        for role, permissions in DEFAULT_ROLE_PERMISSIONS.items():
            conn.execute(
                "INSERT OR IGNORE INTO company_role_permissions(company_id,role,permissions_json,updated_at) VALUES(?,?,?,?)",
                (company_id, role, json.dumps(permissions), now),
            )

    return get_company_context(company_id)


def update_company(
    company_id: str,
    name: Optional[str] = None,
    domain: Optional[str] = None,
    context_updates: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    existing = get_company(company_id)

    if not existing:
        raise ValueError(
            f"Company '{company_id}' was not found"
        )

    context = _merge_context(
        existing["context"],
        context_updates,
    )

    new_name = (
        existing["name"]
        if name is None
        else str(name).strip()
    )

    new_domain = (
        existing["domain"]
        if domain is None
        else str(domain).strip()
    )

    now = _utc_now()

    with _connect() as conn:
        conn.execute(
            """
            UPDATE companies
            SET name = ?, domain = ?, context_json = ?, updated_at = ?
            WHERE company_id = ?
            """,
            (
                new_name,
                new_domain,
                json.dumps(
                    context,
                    ensure_ascii=False,
                    default=str,
                ),
                now,
                company_id,
            ),
        )

    return get_company_context(company_id)

def _next_employee_id(
    conn,
    company_id: str,
    role: str,
) -> str:
    """
    Generate the next unique employee master ID for a company.

    Company admins use ADMxxxx.
    Other users use EMPxxxx.
    """

    prefix = (
        "ADM"
        if str(role or "").strip().lower() == "company_admin"
        else "EMP"
    )

    numbers = []

    for table in (
        "company_users",
        "employee_profiles",
    ):

        rows = conn.execute(
            f"""
            SELECT employee_id
            FROM {table}
            WHERE employee_id LIKE ?
            """,
            (
                f"{prefix}%",
            ),
        ).fetchall()

        for row in rows:

            value = str(
                row["employee_id"]
                if hasattr(row, "keys")
                else row[0]
                or ""
            ).strip()

            if not value.startswith(prefix):
                continue

            suffix = value[
                len(prefix):
            ]

            if suffix.isdigit():
                numbers.append(
                    int(suffix)
                )

    next_number = (
        max(numbers)
        if numbers
        else 0
    ) + 1

    return f"{prefix}{next_number:04d}"


def _sync_employee_profile(
    user: Dict[str, Any],
) -> None:
    """
    Create or update the Employee Master record for a company user.

    Missing employee IDs are generated automatically.
    """

    if not user:
        return

    user_id = str(
        user.get("user_id") or ""
    ).strip()

    company_id = str(
        user.get("company_id") or ""
    ).strip()

    if not user_id or not company_id:
        return

    role = str(
        user.get("role") or "employee"
    ).strip().lower()

    employee_id = str(
        user.get("employee_id") or ""
    ).strip()

    now = _utc_now()

    with _connect() as conn:

        # ----------------------------------------------------
        # Generate an ID when the user does not have one.
        # ----------------------------------------------------

        if not employee_id:

            employee_id = _next_employee_id(
                conn,
                company_id,
                role,
            )

            conn.execute(
                """
                UPDATE company_users
                SET
                    employee_id = ?,
                    updated_at = ?
                WHERE user_id = ?
                  AND company_id = ?
                """,
                (
                    employee_id,
                    now,
                    user_id,
                    company_id,
                ),
            )

        # ----------------------------------------------------
        # Check employee master by ID.
        # ----------------------------------------------------

        existing = conn.execute(
            """
            SELECT employee_id, user_id
            FROM employee_profiles
            WHERE employee_id = ?
              AND company_id = ?
            """,
            (
                employee_id,
                company_id,
            ),
        ).fetchone()

        # ----------------------------------------------------
        # Check employee master by user ID.
        # ----------------------------------------------------

        existing_by_user = conn.execute(
            """
            SELECT employee_id, user_id
            FROM employee_profiles
            WHERE user_id = ?
              AND company_id = ?
            """,
            (
                user_id,
                company_id,
            ),
        ).fetchone()

        # ----------------------------------------------------
        # Update existing profile.
        # ----------------------------------------------------

        if existing or existing_by_user:

            conn.execute(
                """
                UPDATE employee_profiles
                SET
                    employee_id = ?,
                    company_id = ?,
                    user_id = ?,
                    full_name = ?,
                    email = ?,
                    department = ?,
                    role_name = ?,
                    employment_status = ?,
                    updated_at = ?
                WHERE user_id = ?
                  AND company_id = ?
                """,
                (
                    employee_id,
                    company_id,
                    user_id,
                    user.get("name", ""),
                    user.get("email", ""),
                    user.get("department", ""),
                    role,
                    user.get("status", "active"),
                    now,
                    user_id,
                    company_id,
                ),
            )

        # ----------------------------------------------------
        # Create new profile.
        # ----------------------------------------------------

        else:

            conn.execute(
                """
                INSERT INTO employee_profiles (
                    employee_id,
                    company_id,
                    user_id,
                    full_name,
                    email,
                    phone,
                    department,
                    job_title,
                    role_name,
                    manager_employee_id,
                    joining_date,
                    employment_status,
                    location,
                    date_of_birth,
                    leave_entitlement_days,
                    leave_balance_days,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    employee_id,
                    company_id,
                    user_id,
                    user.get("name", ""),
                    user.get("email", ""),
                    "",
                    user.get("department", ""),
                    "",
                    role,
                    "",
                    "",
                    user.get("status", "active"),
                    "",
                    "",
                    20 if role == "employee" else 0,
                    20.0 if role == "employee" else 0.0,
                    now,
                    now,
                ),
            )

        conn.commit()




def add_company_user(
    user_id: str,
    company_id: str,
    name: str,
    email: str = "",
    role: str = "employee",
    department: str = "",
    password_hash: str = "",
    password_salt: str = "",
) -> Dict[str, Any]:

    if not get_company(company_id):
        raise ValueError(
            f"Company '{company_id}' was not found"
        )

    user_id = str(user_id).strip()
    name = str(name).strip()
    email = str(email or "").strip()
    role = (
        str(role).strip().lower()
        or "employee"
    )
    department = str(
        department or ""
    ).strip()

    now = _utc_now()

    if not user_id or not name:
        raise ValueError(
            "user_id and user name are required"
        )

    with _connect() as conn:

        # ----------------------------------------------------
        # Preserve an existing employee ID.
        # Generate one when the user has none.
        # ----------------------------------------------------

        existing = conn.execute(
            """
            SELECT employee_id
            FROM company_users
            WHERE user_id = ?
              AND company_id = ?
            """,
            (
                user_id,
                company_id,
            ),
        ).fetchone()

        employee_id = ""

        if existing:
            employee_id = str(
                existing["employee_id"] or ""
            ).strip()

        if not employee_id:
            employee_id = _next_employee_id(
                conn,
                company_id,
                role,
            )

        # ----------------------------------------------------
        # Insert / update company user.
        #
        # Every column uses an explicit placeholder so the
        # binding order cannot shift accidentally.
        # ----------------------------------------------------

        conn.execute(
            """
            INSERT INTO company_users
            (
                user_id,
                employee_id,
                company_id,
                name,
                email,
                role,
                department,
                status,
                password_hash,
                password_salt,
                created_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )

            ON CONFLICT(user_id) DO UPDATE SET
                employee_id = excluded.employee_id,
                company_id = excluded.company_id,
                name = excluded.name,
                email = excluded.email,
                role = excluded.role,
                department = excluded.department,
                status = excluded.status,

                password_hash =
                    CASE
                        WHEN excluded.password_hash <> ''
                        THEN excluded.password_hash
                        ELSE company_users.password_hash
                    END,

                password_salt =
                    CASE
                        WHEN excluded.password_hash <> ''
                        THEN excluded.password_salt
                        ELSE company_users.password_salt
                    END,

                updated_at = excluded.updated_at
            """,
            (
                user_id,
                employee_id,
                company_id,
                name,
                email,
                role,
                department,
                "active",
                str(password_hash or ""),
                str(password_salt or ""),
                now,
                now,
            ),
        )

        conn.commit()

    user = get_user(user_id)

    _sync_employee_profile(
        user
    )

    return get_user(
        user_id
    )




def get_user(user_id: str) -> Dict[str, Any]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM company_users WHERE user_id = ?",
            (str(user_id).strip(),),
        ).fetchone()

    if not row:
        return {}

    return dict(row)

def list_company_users(
    company_id: str,
) -> List[Dict[str, Any]]:
    initialize_company_store()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                cu.user_id,
                cu.employee_id,
                cu.company_id,
                cu.name,
                cu.email,
                cu.role,
                cu.department,
                cu.status,
                cu.created_at,
                cu.updated_at,
                COALESCE(ep.phone, '') AS phone,
                COALESCE(ep.job_title, '') AS designation
            FROM company_users cu
            LEFT JOIN employee_profiles ep ON ep.user_id = cu.user_id AND ep.company_id = cu.company_id
            WHERE cu.company_id = ?
            ORDER BY cu.name
            """,
            (str(company_id).strip(),),
        ).fetchall()

    return [dict(row) for row in rows]


def get_company(
    company_id: str,
) -> Dict[str, Any]:
    initialize_company_store()

    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE company_id = ?",
            (str(company_id).strip(),),
        ).fetchone()

    if not row:
        return {}

    item = dict(row)

    try:
        item["context"] = json.loads(
            item.get("context_json") or "{}"
        )
    except json.JSONDecodeError:
        item["context"] = {}

    item.pop("context_json", None)

    return item


def list_role_permissions(
    company_id: str,
) -> Dict[str, List[str]]:
    initialize_company_store()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT role, permissions_json
            FROM company_role_permissions
            WHERE company_id = ?
            ORDER BY role
            """,
            (str(company_id).strip(),),
        ).fetchall()

    result: Dict[str, List[str]] = {}

    for row in rows:
        try:
            permissions = json.loads(
                row["permissions_json"] or "[]"
            )
        except json.JSONDecodeError:
            permissions = []

        result[str(row["role"])] = (
            permissions
            if isinstance(permissions, list)
            else []
        )

    return result


def set_role_permissions(
    company_id: str,
    role: str,
    permissions: List[str],
) -> Dict[str, List[str]]:
    initialize_company_store()

    company = get_company(company_id)

    if not company:
        raise ValueError(
            f"Company '{company_id}' was not found"
        )

    role = str(role).strip().lower()

    if role not in DEFAULT_ROLE_PERMISSIONS:
        raise ValueError(
            f"Unsupported role: {role}"
        )

    normalized = []

    for permission in permissions:
        value = str(permission).strip()

        if value and value not in normalized:
            normalized.append(value)

    now = _utc_now()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO company_role_permissions
            (company_id, role, permissions_json, updated_at)
            VALUES (?, ?, ?, ?)

            ON CONFLICT(company_id, role) DO UPDATE SET
                permissions_json = excluded.permissions_json,
                updated_at = excluded.updated_at
            """,
            (
                company_id,
                role,
                json.dumps(normalized),
                now,
            ),
        )

    return list_role_permissions(company_id)


def update_user_status(
    company_id: str,
    user_id: str,
    status: str,
) -> Dict[str, Any]:
    user = get_user(user_id)

    if not user:
        raise ValueError(
            f"Unknown user: {user_id}"
        )

    if user.get("company_id") != company_id:
        raise PermissionError(
            "User does not belong to this company tenant"
        )

    status = str(status).strip().lower()

    if status not in {"active", "inactive"}:
        raise ValueError(
            "status must be active or inactive"
        )

    now = _utc_now()

    with _connect() as conn:
        conn.execute(
            """
            UPDATE company_users
            SET status = ?, updated_at = ?
            WHERE user_id = ? AND company_id = ?
            """,
            (
                status,
                now,
                user["user_id"],
                company_id,
            ),
        )

    return get_user(user["user_id"])


def get_company_context(
    company_id: str,
) -> Dict[str, Any]:
    company = get_company(company_id)

    if not company:
        return {}

    context = dict(
        company.get("context") or {}
    )

    context["company_id"] = company["company_id"]
    context["company_name"] = company["name"]
    context["company_domain"] = company.get(
        "domain",
        "",
    )
    context["updated_at"] = company.get(
        "updated_at"
    )

    # Keep employees out of the generic context by default.
    # Employee data should only be queried when a later
    # workflow/tool actually needs it.
    return context


def authorize_user(
    company_id: str,
    user_id: str,
    allowed_roles: Optional[List[str]] = None,
) -> Dict[str, Any]:
    company = get_company(company_id)

    if not company:
        raise PermissionError(
            f"Unknown company tenant: {company_id}"
        )

    user = get_user(user_id)

    if not user:
        raise PermissionError(
            f"Unknown user: {user_id}"
        )

    if user.get("company_id") != company_id:
        raise PermissionError(
            "User does not belong to this company tenant"
        )

    if user.get("status") != "active":
        raise PermissionError(
            "User account is not active"
        )

    if allowed_roles:
        roles = {
            str(role).lower()
            for role in allowed_roles
        }

        if (
            str(user.get("role", "")).lower()
            not in roles
        ):
            raise PermissionError(
                "User role is not authorized for this operation"
            )

    return user


def get_user_by_email(
    company_id: str,
    email: str,
) -> Dict[str, Any]:
    initialize_company_store()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM company_users
            WHERE company_id = ?
              AND lower(email) = lower(?)
            """,
            (
                str(company_id).strip(),
                str(email).strip(),
            ),
        ).fetchone()

    return dict(row) if row else {}


def set_user_auth_state(
    user_id: str,
    *,
    password_hash: Optional[str] = None,
    password_salt: Optional[str] = None,
    failed_attempts: Optional[int] = None,
    locked_until: Optional[str] = None,
    last_login_at: Optional[str] = None,
    account_status: Optional[str] = None,
) -> Dict[str, Any]:
    user = get_user(user_id)

    if not user:
        raise ValueError(
            f"Unknown user: {user_id}"
        )

    assignments = []
    values: List[Any] = []

    if password_hash is not None:
        assignments.append("password_hash = ?")
        values.append(password_hash)

    if password_salt is not None:
        assignments.append("password_salt = ?")
        values.append(password_salt)

    if failed_attempts is not None:
        assignments.append("failed_attempts = ?")
        values.append(int(failed_attempts))

    if locked_until is not None:
        assignments.append("locked_until = ?")
        values.append(str(locked_until))

    if last_login_at is not None:
        assignments.append("last_login_at = ?")
        values.append(str(last_login_at))

    if account_status is not None:
        assignments.append("account_status = ?")
        values.append(str(account_status))

    if assignments:
        now = _utc_now()

        assignments.append("updated_at = ?")
        values.append(now)

        values.append(user_id)

        with _connect() as conn:
            conn.execute(
                f"""
                UPDATE company_users
                SET {', '.join(assignments)}
                WHERE user_id = ?
                """,
                tuple(values),
            )

    return get_user(user_id)

def ensure_demo_company() -> None:
    initialize_company_store()

    existing_company = get_company("demo_company")

    if existing_company:
        # Existing users ni Employee Master ki sync cheyyali.
        users = list_company_users("demo_company")

        for user in users:
            _sync_employee_profile(user)

        _ensure_demo_credentials()
        from company.catalog_service import seed_demo_catalog
        seed_demo_catalog("demo_company")
        return

    register_company(
        company_id="demo_company",
        name="Demo Enterprise",
        domain="demo.local",
        context={
            "departments": [
                "HR",
                "IT",
                "Finance",
                "Procurement",
                "Recruitment",
            ],
            "policies": {
                "leave": {
                    "annual_leave_days": 20,
                    "manager_approval_required": True,
                },
                "laptop_budget_inr": 120000,
                "finance_available_budget_inr": 200000,
                "finance_currency": "INR",
            },
            "approval_rules": {
                "purchase_above_inr": 100000,
            },
            "locations": [
                "Vijayawada",
                "Hyderabad",
            ],
            "organization_metadata": {
                "industry": "Technology",
                "timezone": "Asia/Kolkata",
            },
        },
    )

    add_company_user(
        user_id="demo_admin",
        company_id="demo_company",
        name="Demo Company Admin",
        email="admin@demo.local",
        role="company_admin",
    )

    add_company_user(
        user_id="demo_employee",
        company_id="demo_company",
        name="Demo Employee",
        email="employee@demo.local",
        role="employee",
        department="IT",
    )

    _ensure_demo_credentials()
    from company.catalog_service import seed_demo_catalog
    seed_demo_catalog("demo_company")


def _ensure_demo_credentials() -> None:
    """Seed development-only passwords without overwriting existing user passwords."""
    try:
        from company.auth import hash_password
    except Exception:
        return

    demo = {
        "demo_admin": "Admin@1234",
        "demo_employee": "Employee@1234",
    }

    for user_id, password in demo.items():
        user = get_user(user_id)

        if user and not user.get("password_hash"):
            salt, password_hash = hash_password(
                password
            )

            set_user_auth_state(
                user_id,
                password_hash=password_hash,
                password_salt=salt,
                failed_attempts=0,
                locked_until="",
            )


initialize_company_store()
