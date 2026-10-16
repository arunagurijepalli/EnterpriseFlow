"""Tenant-safe notification read-state operations."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from company.store import DB_PATH, authorize_user, initialize_company_store


def mark_notification_read(company_id: str, user_id: str, notification_id: int) -> bool:
    authorize_user(company_id, user_id)
    initialize_company_store()
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.execute("UPDATE notifications SET read_at=? WHERE company_id=? AND user_id=? AND notification_id=? AND read_at IS NULL", (now, company_id, user_id, int(notification_id)))
    return cursor.rowcount > 0
