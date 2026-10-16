from __future__ import annotations
from contextlib import contextmanager

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List

from company.store import DB_PATH, initialize_company_store, authorize_user


@contextmanager
def _connect():
    """Yield a configured connection and always close it."""
    initialize_company_store()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def seed_demo_catalog(company_id: str) -> None:
    """Fill missing demo catalog entries/specs without overwriting admin edits.

    Prices and specifications below are editable demo planning baselines, not
    supplier quotes. Existing price, stock, currency and any already-entered
    specification keys always win over these defaults.
    """
    if str(company_id or "").strip() != "demo_company":
        return

    rows = [
        ("laptop", "AI Pro Laptop", 145000, 3, {
            "catalog_note": "Demo planning baseline only; validate final model/specification and supplier quote before ordering.",
            "sku": "DEMO-DEV-AI-001",
            "manufacturer": "Approved business-class OEM (select supplier/model in Admin Console)",
            "processor": "Intel Core i7 / AMD Ryzen 7 performance-class equivalent; exact SKU requires supplier quote",
            "memory": "32 GB DDR5 RAM",
            "ram": "32 GB",
            "memory_upgrade_path": "Target 64 GB where the selected model supports it; verify model-specific maximum",
            "storage": "1 TB NVMe SSD",
            "storage_expandability": "Second SSD slot/upgrade options to be confirmed for selected SKU",
            "gpu": "Dedicated NVIDIA RTX 4070-class GPU (equivalent model must be confirmed on quote)",
            "gpu_memory": "8 GB-class dedicated graphics memory; supplier to confirm exact GPU",
            "display": "15.6-inch FHD/QHD IPS; exact resolution/brightness to be selected from supplier offering",
            "operating_system": "Windows 11 Pro (company-licensed image)",
            "wireless": "Wi-Fi 6E or better; Bluetooth 5.x or better, model dependent",
            "ports": "USB-C with charging/display output, USB-A, HDMI and audio; confirm exact port count per SKU",
            "camera_audio": "1080p webcam, microphone array and speakers; privacy shutter preferred",
            "battery": "Business-class battery; capacity and tested runtime must be confirmed on supplier datasheet",
            "weight": "Model-dependent; confirm shipping and carry weight from supplier datasheet",
            "warranty": "3-year business warranty target; on-site coverage subject to supplier quote",
            "support_sla": "Next-business-day on-site support preferred where offered; confirm contract",
            "use_case": "AI/ML development, local experimentation, GPU workloads and demanding IDE/container workloads",
            "approval_note": "High-cost purchase; apply company laptop budget and approval policy before purchase",
            "price_basis": "INR 145,000 demo estimate; not a live supplier quotation",
        }),
        ("laptop", "Developer Laptop", 95000, 7, {
            "catalog_note": "Demo planning baseline only; validate final model/specification and supplier quote before ordering.",
            "sku": "DEMO-DEV-STD-001",
            "manufacturer": "Approved business-class OEM (select supplier/model in Admin Console)",
            "processor": "Intel Core i5 / AMD Ryzen 5 or better, current supported generation; exact SKU requires supplier quote",
            "memory": "16 GB DDR5 RAM",
            "ram": "16 GB",
            "memory_upgrade_path": "32 GB target where supported; verify whether memory is upgradeable",
            "storage": "512 GB NVMe SSD",
            "storage_expandability": "Confirm additional SSD slot or upgrade path for selected SKU",
            "gpu": "Integrated graphics suitable for standard software development",
            "gpu_memory": "Shared system memory; no dedicated GPU assumed",
            "display": "14-15.6-inch FHD IPS anti-glare display; exact panel to be confirmed",
            "operating_system": "Windows 11 Pro (company-licensed image)",
            "wireless": "Wi-Fi 6 or better; Bluetooth 5.x or better, model dependent",
            "ports": "USB-C, USB-A, HDMI and audio; confirm exact port count per SKU",
            "camera_audio": "1080p webcam, microphone and speakers preferred",
            "battery": "Business-class battery; capacity/runtime to be confirmed from supplier datasheet",
            "weight": "Model-dependent; confirm supplier datasheet",
            "warranty": "3-year business warranty target; coverage subject to supplier quote",
            "support_sla": "Business support; on-site SLA to be confirmed with approved supplier",
            "use_case": "Software development, IDEs, containers, web development and general coding",
            "approval_note": "Apply company laptop budget and approval policy before purchase",
            "price_basis": "INR 95,000 demo estimate; not a live supplier quotation",
        }),
        ("laptop", "Business Laptop", 65000, 12, {
            "catalog_note": "Demo planning baseline only; validate final model/specification and supplier quote before ordering.",
            "sku": "DEMO-BIZ-STD-001",
            "manufacturer": "Approved business-class OEM (select supplier/model in Admin Console)",
            "processor": "Intel Core i5 / equivalent supported business processor; exact SKU requires supplier quote",
            "memory": "16 GB RAM target",
            "ram": "16 GB",
            "memory_upgrade_path": "Confirm supported maximum and upgradeability for selected SKU",
            "storage": "512 GB SSD target; NVMe preferred",
            "storage_expandability": "Confirm selected model storage upgrade path",
            "gpu": "Integrated graphics for productivity and meeting applications",
            "display": "14-inch FHD IPS anti-glare display target; model dependent",
            "operating_system": "Windows 11 Pro (company-licensed image)",
            "wireless": "Wi-Fi 6 or better; Bluetooth 5.x or better, model dependent",
            "ports": "USB-C, USB-A, HDMI and audio; verify exact supplier configuration",
            "camera_audio": "Webcam, microphone and speakers for business meetings",
            "battery": "Business-class battery; runtime to be confirmed from supplier datasheet",
            "weight": "Model-dependent; confirm supplier datasheet",
            "warranty": "3-year business warranty target; coverage subject to supplier quote",
            "support_sla": "Business support; SLA to be confirmed with approved supplier",
            "use_case": "Office work, browser-based business applications, meetings and everyday productivity",
            "approval_note": "Apply company laptop budget and approval policy before purchase",
            "price_basis": "INR 65,000 demo estimate; not a live supplier quotation",
        }),
    ]

    with _connect() as conn:
        now = datetime.now(timezone.utc).isoformat()
        for item_type, model, price, stock, defaults in rows:
            existing = conn.execute(
                "SELECT inventory_id,specs_json FROM company_inventory "
                "WHERE company_id=? AND lower(item_type)=lower(?) AND lower(model)=lower(?) LIMIT 1",
                (company_id, item_type, model),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO company_inventory "
                    "(company_id,item_type,model,unit_price,currency,quantity_available,specs_json,status,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,'active',?,?)",
                    (company_id, item_type, model, price, "INR", stock,
                     json.dumps(defaults, ensure_ascii=False), now, now),
                )
            else:
                # Enrich older demo rows with missing spec keys. Existing admin
                # values take precedence, and price/stock/currency are untouched.
                try:
                    current_specs = json.loads(existing["specs_json"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    current_specs = {}
                if not isinstance(current_specs, dict):
                    current_specs = {}
                merged_specs = {**defaults, **current_specs}
                if merged_specs != current_specs:
                    conn.execute(
                        "UPDATE company_inventory SET specs_json=?,updated_at=? WHERE company_id=? AND inventory_id=?",
                        (json.dumps(merged_specs, ensure_ascii=False), now, company_id, existing["inventory_id"]),
                    )

        conn.executemany(
            "INSERT OR IGNORE INTO company_vendors "
            "(company_id,name,rating,delivery_days,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            [(company_id, "Enterprise Systems Ltd", 4.5, 5, "active", now, now),
             (company_id, "Tech Solutions India", 4.3, 7, "active", now, now)],
        )


def ensure_demo_company_defaults(company_id: str) -> None:
    """Fill missing demo workspace profile/policy values, never overwrite admin edits."""
    if str(company_id or "").strip() != "demo_company":
        return
    from company.store import get_company, update_company
    company = get_company(company_id)
    if not company:
        return
    context = dict(company.get("context") or {})
    changed = False

    departments = context.get("departments")
    if not isinstance(departments, list) or not departments:
        context["departments"] = ["HR", "IT", "Finance", "Procurement", "Recruitment"]
        changed = True
    locations = context.get("locations")
    if not isinstance(locations, list) or not locations:
        context["locations"] = ["Vijayawada", "Hyderabad"]
        changed = True

    metadata = dict(context.get("organization_metadata") or {})
    defaults = {
        "industry": "Technology",
        "timezone": "Asia/Kolkata",
        "headquarters": "Vijayawada, Andhra Pradesh, India",
        "website": "https://demo.local",
        "company_description": "Enterprise technology workspace for software delivery and employee services.",
        "hr_contact_email": "hr@demo.local",
        "it_support_email": "it-support@demo.local",
        "support_phone": "+91 00000 00000 (demo placeholder)",
    }
    for key, value in defaults.items():
        if not str(metadata.get(key) or "").strip():
            metadata[key] = value
            changed = True
    context["organization_metadata"] = metadata

    policies = dict(context.get("policies") or {})
    leave = dict(policies.get("leave") or {})
    for key, value in {"annual_leave_days": 20, "manager_approval_required": True, "count_weekends": False}.items():
        if key not in leave:
            leave[key] = value
            changed = True
    if not leave.get("leave_types"):
        leave["leave_types"] = ["Annual Leave", "Sick Leave", "Casual Leave"]
        changed = True
    policies["leave"] = leave
    for key, value in {"laptop_budget_inr": 200000, "finance_available_budget_inr": 200000, "finance_currency": "INR"}.items():
        if key not in policies:
            policies[key] = value
            changed = True
    context["policies"] = policies

    approval_rules = dict(context.get("approval_rules") or {})
    if "purchase_above_inr" not in approval_rules:
        approval_rules["purchase_above_inr"] = 100000
        changed = True
    context["approval_rules"] = approval_rules

    if changed:
        update_company(company_id, context_updates=context)
    seed_demo_catalog(company_id)


def list_inventory(company_id: str, item_type: str = "") -> List[Dict[str, Any]]:
    with _connect() as conn:
        query = "SELECT inventory_id,item_type,model,unit_price,currency,quantity_available,specs_json FROM company_inventory WHERE company_id=? AND status='active'"
        params: list[Any] = [company_id]
        if item_type:
            query += " AND lower(item_type)=lower(?)"
            params.append(item_type)
        query += " ORDER BY item_type,model"
        rows = conn.execute(query, tuple(params)).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        try:
            item["specifications"] = json.loads(item.pop("specs_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["specifications"] = {}
        results.append(item)
    return results


def list_vendors(company_id: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT name,rating,delivery_days FROM company_vendors WHERE company_id=? AND status='active' ORDER BY name", (company_id,)).fetchall()
    return [dict(row) for row in rows]


def upsert_vendor_as_admin(company_id: str, user_id: str, name: str,
                           rating: float | None = None,
                           delivery_days: int | None = None) -> None:
    actor = authorize_user(company_id, user_id)
    if str(actor.get("role") or "").lower() not in {"company_admin", "procurement_admin"}:
        raise PermissionError("Only Procurement or Company Admin can manage vendors.")
    name = str(name or "").strip()
    if not name:
        raise ValueError("Vendor name is required.")
    if rating is not None and not 0 <= float(rating) <= 5:
        raise ValueError("Vendor rating must be between 0 and 5.")
    if delivery_days is not None and int(delivery_days) <= 0:
        raise ValueError("Delivery days must be a positive whole number.")
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO company_vendors(company_id,name,rating,delivery_days,status,created_at,updated_at) VALUES(?,?,?,?, 'active',?,?) ON CONFLICT(company_id,name) DO UPDATE SET rating=excluded.rating,delivery_days=excluded.delivery_days,status='active',updated_at=excluded.updated_at",
            (company_id, name, float(rating) if rating is not None else None, int(delivery_days) if delivery_days is not None else None, now, now),
        )
        conn.execute("INSERT INTO audit_logs(company_id,user_id,action,resource_type,resource_id,details_json,created_at) VALUES(?,?,?,?,?,?,?)", (company_id, user_id, "vendor_saved", "company_vendor", name, json.dumps({"rating": rating, "delivery_days": delivery_days}), now))


def upsert_inventory_as_admin(company_id: str, user_id: str, item_type: str, model: str, unit_price: float, currency: str, quantity: int, specs: Dict[str, Any] | None = None) -> None:
    user = authorize_user(company_id, user_id)
    if str(user.get("role", "")).lower() not in {"company_admin", "procurement_admin"}:
        raise PermissionError("Only Procurement or Company Admin can manage inventory.")
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO company_inventory (company_id,item_type,model,unit_price,currency,quantity_available,specs_json,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'active',?,?) ON CONFLICT(company_id,item_type,model) DO UPDATE SET unit_price=excluded.unit_price,currency=excluded.currency,quantity_available=excluded.quantity_available,specs_json=excluded.specs_json,status='active',updated_at=excluded.updated_at",
            (company_id, item_type.strip(), model.strip(), float(unit_price), currency.strip(), int(quantity), json.dumps(specs or {}, ensure_ascii=False), now, now),
        )

