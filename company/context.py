from __future__ import annotations

from typing import Any, Dict, Optional

from company.store import authorize_user, get_company_context


def load_tenant_context(
    company_id: Optional[str],
    user_id: Optional[str],
    user_role: Optional[str],
) -> Dict[str, Any]:
    """Load tenant-scoped context and enforce basic user/company isolation.

    Legacy direct calls without a company_id remain supported for development.
    Deployed/API calls should always provide company_id + user_id.
    """

    if not company_id:
        return {
            "tenant_mode": False,
            "company_id": "",
            "company_name": "",
            "user_id": str(user_id or ""),
            "user_role": str(user_role or ""),
            "authorized": True,
            "context": {},
        }

    user = None

    if user_id:
        user = authorize_user(company_id, user_id)
    else:
        raise PermissionError(
            "user_id is required when company_id is provided"
        )

    # The stored role is authoritative. Do not trust a caller-provided role.
    effective_role = str(user.get("role", "employee"))

    return {
        "tenant_mode": True,
        "company_id": company_id,
        "company_name": "",
        "user_id": user_id,
        "user_role": effective_role,
        "user_name": user.get("name", ""),
        "user_department": user.get("department", ""),
        "authorized": True,
        "context": get_company_context(company_id),
    }
