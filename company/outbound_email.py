"""Environment-configured outbound email with tenant-scoped delivery records."""
from __future__ import annotations

import os
import smtplib
import sqlite3
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from company.store import DB_PATH, initialize_company_store, authorize_user


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def email_configuration_status() -> dict[str, Any]:
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip()
    ready = bool(host and sender and os.getenv("SMTP_PORT", "").strip())
    return {
        "provider": "SMTP" if ready else "Not configured",
        "configured": ready,
        "host": host,
        "port": os.getenv("SMTP_PORT", "").strip(),
        "from_email": sender,
        "from_name": os.getenv("SMTP_FROM_NAME", "EnterpriseFlow").strip(),
        "tls": os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"},
        "authenticated": bool(username and password),
    }


def _log_delivery(company_id: str, recipient: str, event_type: str, subject: str,
                  status: str, failure_reason: str = "", related_id: str = "") -> int:
    initialize_company_store()
    now = _now()
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.execute(
            "INSERT INTO email_delivery_logs(company_id,recipient,event_type,subject,status,created_at,sent_at,failure_reason,related_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (company_id, recipient, event_type, subject, status, now,
             now if status == "sent" else "", failure_reason, str(related_id or "")),
        )
        return int(cursor.lastrowid)


def send_transactional_email(company_id: str, recipient: str, event_type: str,
                              subject: str, body: str, related_id: str = "") -> dict[str, Any]:
    """Attempt one real SMTP delivery; missing config and errors are persisted honestly."""
    recipient = str(recipient or "").strip()
    if not recipient or "@" not in recipient:
        delivery_id = _log_delivery(company_id, recipient, event_type, subject,
                                    "failed", "Please enter a valid email address.", related_id)
        return {"status": "failed", "delivery_id": delivery_id,
                "message": "Please enter a valid email address."}
    config = email_configuration_status()
    if not config["configured"]:
        message = "Email service is not configured. Configure SMTP/provider settings to enable outbound email."
        delivery_id = _log_delivery(company_id, recipient, event_type, subject,
                                    "not_configured", message, related_id)
        return {"status": "not_configured", "delivery_id": delivery_id, "message": message}
    try:
        mail = EmailMessage()
        sender_name = config["from_name"]
        mail["From"] = f"{sender_name} <{config['from_email']}>" if sender_name else config["from_email"]
        mail["To"] = recipient
        mail["Subject"] = str(subject)
        mail.set_content(str(body))
        port = int(config["port"])
        if config["tls"]:
            with smtplib.SMTP(config["host"], port, timeout=15) as server:
                server.starttls()
                if config["authenticated"]:
                    server.login(os.getenv("SMTP_USERNAME", ""), os.getenv("SMTP_PASSWORD", ""))
                server.send_message(mail)
        else:
            with smtplib.SMTP_SSL(config["host"], port, timeout=15) as server:
                if config["authenticated"]:
                    server.login(os.getenv("SMTP_USERNAME", ""), os.getenv("SMTP_PASSWORD", ""))
                server.send_message(mail)
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        # Avoid persisting provider response text, which can contain account details.
        reason = f"SMTP delivery failed ({type(exc).__name__}). Check SMTP settings and provider logs."
        delivery_id = _log_delivery(company_id, recipient, event_type, subject,
                                    "failed", reason, related_id)
        return {"status": "failed", "delivery_id": delivery_id,
                "message": "The email provider could not deliver this message. Check SMTP settings and try again."}
    delivery_id = _log_delivery(company_id, recipient, event_type, subject,
                                "sent", related_id=related_id)
    return {"status": "sent", "delivery_id": delivery_id, "message": "Email delivered."}


def send_admin_test_email(company_id: str, admin_user_id: str) -> dict[str, Any]:
    admin = authorize_user(company_id, admin_user_id, allowed_roles=["company_admin"])
    return send_transactional_email(
        company_id, str(admin.get("email") or ""), "test_email",
        "EnterpriseFlow email configuration test",
        "This test message confirms that the configured EnterpriseFlow email provider can deliver email.",
    )


def list_email_deliveries(company_id: str, user_id: str, limit: int = 200) -> list[dict[str, Any]]:
    authorize_user(company_id, user_id, allowed_roles=["company_admin"])
    initialize_company_store()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT delivery_id,recipient,event_type,subject,status,created_at,sent_at,failure_reason,related_id FROM email_delivery_logs WHERE company_id=? ORDER BY delivery_id DESC LIMIT ?",
            (company_id, max(1, min(int(limit), 1000))),
        ).fetchall()
    return [dict(row) for row in rows]
