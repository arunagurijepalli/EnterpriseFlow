import sqlite3

import pytest

from company import store, registration_service, employee_portfolio_service
from company.store import register_company, add_company_user
from company import auth
from company.auth import authenticate_user_by_email


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db = tmp_path / "test_company.db"
    monkeypatch.setattr(store, "DB_PATH", db)
    monkeypatch.setattr(registration_service, "DB_PATH", db)
    monkeypatch.setattr(auth, "DB_PATH", db)
    monkeypatch.setattr(employee_portfolio_service, "DB_PATH", db)
    store.initialize_company_store()
    register_company("tenant_a", "Tenant A", domain="tenant-a.example", context={"departments": ["Engineering", "HR"]})
    yield db


def test_registration_creates_user_and_employee_profile(isolated_db):
    created = registration_service.register_employee("Test Employee", "test@tenant-a.example", "secure-password", "Engineering")
    assert created["company_id"] == "tenant_a"
    assert created["employee_id"].startswith("EMP")
    conn = sqlite3.connect(isolated_db)
    try:
        user = conn.execute("SELECT role, password_hash, account_status FROM company_users WHERE user_id=?", (created["user_id"],)).fetchone()
        profile = conn.execute("SELECT employee_id, company_id FROM employee_profiles WHERE user_id=?", (created["user_id"],)).fetchone()
    finally:
        conn.close()
    assert user[0] == "employee"
    assert user[1] != "secure-password" and user[1]
    assert user[2] == "active"
    assert profile == (created["employee_id"], "tenant_a")
    assert authenticate_user_by_email("test@tenant-a.example", "secure-password")["user_id"] == created["user_id"]


def test_duplicate_registration_and_unapproved_domain_rejected(isolated_db):
    registration_service.register_employee("Test Employee", "test@tenant-a.example", "secure-password")
    with pytest.raises(ValueError, match="already exists"):
        registration_service.register_employee("Other Name", "TEST@tenant-a.example", "other-password")
    with pytest.raises(ValueError, match="unavailable"):
        registration_service.register_employee("Other Name", "user@unknown.example", "other-password")


def test_feedback_is_scoped_to_authenticated_user(isolated_db):
    one = registration_service.register_employee("One Employee", "one@tenant-a.example", "secure-password")
    two = registration_service.register_employee("Two Employee", "two@tenant-a.example", "secure-password")
    employee_portfolio_service.create_performance("tenant_a", one["employee_id"], "Q3 2026", 4.5, goals="Ship release", achievements_summary="Delivered release", manager_feedback="Great work", status="completed", reviewer_user_id="hr-1", strengths="Collaboration")
    assert len(employee_portfolio_service.get_my_published_performance("tenant_a", one["user_id"])) == 1
    assert employee_portfolio_service.get_my_published_performance("tenant_a", two["user_id"]) == []



def test_registration_syncs_contact_and_designation_to_admin_directory(isolated_db):
    created = registration_service.register_employee(
        "Directory Employee",
        "directory@tenant-a.example",
        "secure-password",
        "Engineering",
        phone="9876543210",
        designation="Software Intern",
        employee_id="ENG-204",
    )
    rows = store.list_company_users("tenant_a")
    directory_row = next(row for row in rows if row["user_id"] == created["user_id"])
    assert directory_row["employee_id"] == "ENG-204"
    assert directory_row["phone"] == "9876543210"
    assert directory_row["designation"] == "Software Intern"

    with pytest.raises(ValueError, match="already in use"):
        registration_service.register_employee(
            "Another Employee",
            "another@tenant-a.example",
            "secure-password",
            "Engineering",
            employee_id="ENG-204",
        )
