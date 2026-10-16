"""Administrative helpers for company onboarding and updates."""

import os
from typing import Any, Dict, List, Optional

from company.auth import set_password
from company.auth_tokens import issue_account_token
from company.outbound_email import send_transactional_email

from company.store import (
    add_company_user,
    authorize_user,
    register_company,
    set_role_permissions,
    update_company,
    update_user_status,
)


def create_company(
    admin_user_id: str,
    company_id: str,
    name: str,
    domain: str = "",
    context: Optional[Dict[str, Any]] = None,
    admin_name: str = "Company Admin",
    admin_email: str = "",
) -> Dict[str, Any]:
    company = register_company(company_id, name, domain, context)
    add_company_user(
        user_id=admin_user_id,
        company_id=company_id,
        name=admin_name,
        email=admin_email,
        role="company_admin",
    )
    return company


def update_company_as_admin(
    company_id: str,
    admin_user_id: str,
    name: Optional[str] = None,
    domain: Optional[str] = None,
    context_updates: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    authorize_user(
        company_id,
        admin_user_id,
        allowed_roles=["company_admin"],
    )
    return update_company(
        company_id=company_id,
        name=name,
        domain=domain,
        context_updates=context_updates,
    )


def add_or_update_user_as_admin(
    company_id: str,
    admin_user_id: str,
    user_id: str,
    name: str,
    email: str = "",
    role: str = "employee",
    department: str = "",
    password: str = "",
) -> Dict[str, Any]:

    authorize_user(
        company_id,
        admin_user_id,
        allowed_roles=["company_admin"],
    )

    if not str(email or "").strip() or "@" not in str(email):
        raise ValueError("Please enter a valid work email address.")
    from company.store import get_user
    existing_user = get_user(user_id)
    user = add_company_user(
        user_id=user_id,
        company_id=company_id,
        name=name,
        email=email,
        role=role,
        department=department,
    )

    if str(password or "").strip():

        set_password(
            user_id,
            password.strip(),
        )

        user = add_company_user(
            user_id=user_id,
            company_id=company_id,
            name=name,
            email=email,
            role=role,
            department=department,
        )

    elif not existing_user:
        from company.store import set_user_auth_state
        set_user_auth_state(user_id, account_status="pending_activation")
        token = issue_account_token(company_id, user_id, "activation", lifetime_minutes=1440)
        base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:18767").rstrip("/")
        link = f"{base_url}/?activation_token={token}"
        delivery = send_transactional_email(
            company_id, str(email).strip(), "employee_invitation",
            "Activate your EnterpriseFlow account",
            f"Hello {name},\n\nYour company invited you to EnterpriseFlow. Open this one-time link to set your password and activate your account:\n{link}\n\nThis link expires in 24 hours.",
            related_id=user_id,
        )
        user["invitation_status"] = delivery["status"]
        user["invitation_message"] = delivery["message"]

    return user




def change_user_status_as_admin(
    company_id: str,
    admin_user_id: str,
    user_id: str,
    status: str,
) -> Dict[str, Any]:
    authorize_user(
        company_id,
        admin_user_id,
        allowed_roles=["company_admin"],
    )
    if user_id == admin_user_id and status == "inactive":
        raise ValueError("Company admin cannot deactivate their own active account")
    return update_user_status(company_id, user_id, status)


def set_role_permissions_as_admin(
    company_id: str,
    admin_user_id: str,
    role: str,
    permissions: List[str],
) -> Dict[str, List[str]]:
    authorize_user(
        company_id,
        admin_user_id,
        allowed_roles=["company_admin"],
    )
    return set_role_permissions(company_id, role, permissions)
