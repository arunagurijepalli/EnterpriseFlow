# company/employee_schema.py

import sqlite3


def initialize_employee_schema(conn: sqlite3.Connection) -> None:
    """
    Creates employee master/profile and employee service history tables.
    Safe to run multiple times because IF NOT EXISTS is used.
    """

    cursor = conn.cursor()

    # ============================================================
    # EMPLOYEE MASTER
    # ============================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_profiles (
            employee_id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            user_id TEXT NOT NULL UNIQUE,

            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,

            department TEXT,
            job_title TEXT,
            role_name TEXT,
            manager_employee_id TEXT,

            joining_date TEXT,
            employment_status TEXT DEFAULT 'active',

            location TEXT,
            date_of_birth TEXT,

            leave_entitlement_days INTEGER DEFAULT 0,
            leave_balance_days REAL DEFAULT 0,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,

            FOREIGN KEY (company_id)
                REFERENCES companies(company_id),

            FOREIGN KEY (user_id)
                REFERENCES company_users(user_id)
        )
        """
    )

    # ============================================================
    # EMPLOYEE SERVICE HISTORY
    # ============================================================
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_service_records (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,

            employee_id TEXT NOT NULL,
            company_id TEXT NOT NULL,

            service_area TEXT NOT NULL,
            service_type TEXT NOT NULL,
            action_type TEXT NOT NULL,

            description TEXT,

            status TEXT,
            decision TEXT,

            workflow_id TEXT,
            approval_id INTEGER,

            agent_name TEXT,
            tool_name TEXT,

            request_data_json TEXT,
            result_data_json TEXT,

            performed_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,

            FOREIGN KEY (employee_id)
                REFERENCES employee_profiles(employee_id),

            FOREIGN KEY (company_id)
                REFERENCES companies(company_id)
        )
        """
    )

    # Dedicated leave records are the source of truth for leave status.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            leave_request_id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            employee_id TEXT NOT NULL,
            leave_type TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            requested_days REAL NOT NULL,
            reason TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending_approval',
            workflow_id TEXT NOT NULL,
            approval_id INTEGER,
            approver_user_id TEXT DEFAULT '',
            decision_reason TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id),
            FOREIGN KEY(user_id) REFERENCES company_users(user_id),
            FOREIGN KEY(employee_id) REFERENCES employee_profiles(employee_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_leave_requests_employee
        ON leave_requests(company_id, user_id, created_at)
        """
    )
    
    # Employee-specific hidden leave history.
    # Original leave requests and audit records remain unchanged.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS leave_history_hidden (
            company_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            leave_request_id TEXT NOT NULL,
            hidden_at TEXT NOT NULL,
            PRIMARY KEY (company_id, user_id, leave_request_id),
            FOREIGN KEY (company_id) REFERENCES companies(company_id),
            FOREIGN KEY (user_id) REFERENCES company_users(user_id),
            FOREIGN KEY (leave_request_id)
                REFERENCES leave_requests(leave_request_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            workflow_id TEXT DEFAULT '',
            notification_type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            resource_type TEXT DEFAULT '',
            resource_id TEXT DEFAULT '',
            read_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id),
            FOREIGN KEY(user_id) REFERENCES company_users(user_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS email_delivery_logs (
            delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL,
            recipient TEXT NOT NULL,
            event_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sent_at TEXT DEFAULT '',
            failure_reason TEXT DEFAULT '',
            related_id TEXT DEFAULT '',
            FOREIGN KEY(company_id) REFERENCES companies(company_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS account_tokens (
            token_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            token_type TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES company_users(user_id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS department_requests (
            request_id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            service_area TEXT NOT NULL,
            request_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount REAL,
            currency TEXT DEFAULT '',
            status TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            approval_id INTEGER,
            approver_user_id TEXT DEFAULT '',
            decision_reason TEXT DEFAULT '',
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id),
            FOREIGN KEY(user_id) REFERENCES company_users(user_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_department_requests_owner
        ON department_requests(company_id, user_id, service_area, created_at)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notifications_inbox
        ON notifications(company_id, user_id, read_at, created_at)
        """
    )

    # ============================================================
    # INDEXES
    # ============================================================

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_profiles_company
        ON employee_profiles(company_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_service_employee
        ON employee_service_records(employee_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_service_company
        ON employee_service_records(company_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_service_area
        ON employee_service_records(service_area)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_service_workflow
        ON employee_service_records(workflow_id)
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_service_time
        ON employee_service_records(performed_at)
        """
    )

    conn.commit()
