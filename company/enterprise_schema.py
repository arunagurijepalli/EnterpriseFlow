"""Phase 1 normalized enterprise data schema."""

from __future__ import annotations
import sqlite3


def initialize_enterprise_schema(conn: sqlite3.Connection) -> None:
    statements = [
        """CREATE TABLE IF NOT EXISTS company_departments (
            department_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, name TEXT NOT NULL,
            description TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(company_id, name),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS company_roles (
            role_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, name TEXT NOT NULL,
            description TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(company_id, name),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS permissions (
            permission_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, permission_key TEXT NOT NULL,
            description TEXT DEFAULT '', created_at TEXT NOT NULL,
            UNIQUE(company_id, permission_key),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS role_permissions (
            company_id TEXT NOT NULL, role_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(company_id, role_id, permission_id),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY(role_id) REFERENCES company_roles(role_id) ON DELETE CASCADE,
            FOREIGN KEY(permission_id) REFERENCES permissions(permission_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS company_agents (
            agent_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, agent_key TEXT NOT NULL, name TEXT NOT NULL,
            description TEXT DEFAULT '', agent_type TEXT NOT NULL DEFAULT 'specialist',
            status TEXT NOT NULL DEFAULT 'active',
            configuration_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(company_id, agent_key),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS agent_departments (
            company_id TEXT NOT NULL, agent_id INTEGER NOT NULL,
            department_id INTEGER NOT NULL,
            PRIMARY KEY(company_id, agent_id, department_id),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY(agent_id) REFERENCES company_agents(agent_id) ON DELETE CASCADE,
            FOREIGN KEY(department_id) REFERENCES company_departments(department_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS company_tools (
            tool_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, tool_key TEXT NOT NULL, name TEXT NOT NULL,
            description TEXT DEFAULT '', department TEXT DEFAULT '',
            risk_level TEXT NOT NULL DEFAULT 'low',
            status TEXT NOT NULL DEFAULT 'active',
            configuration_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(company_id, tool_key),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS company_inventory (
            inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, item_type TEXT NOT NULL, model TEXT NOT NULL,
            unit_price REAL NOT NULL, currency TEXT NOT NULL, quantity_available INTEGER NOT NULL DEFAULT 0,
            specs_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(company_id, item_type, model),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS company_vendors (
            vendor_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, name TEXT NOT NULL, rating REAL, delivery_days INTEGER,
            status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(company_id, name),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS agent_tools (
            company_id TEXT NOT NULL, agent_id INTEGER NOT NULL, tool_id INTEGER NOT NULL,
            PRIMARY KEY(company_id, agent_id, tool_id),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY(agent_id) REFERENCES company_agents(agent_id) ON DELETE CASCADE,
            FOREIGN KEY(tool_id) REFERENCES company_tools(tool_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS policies (
            policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, policy_key TEXT NOT NULL, name TEXT NOT NULL,
            description TEXT DEFAULT '', department TEXT DEFAULT '', category TEXT DEFAULT '',
            priority TEXT NOT NULL DEFAULT 'medium', risk_level TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'active', effective_from TEXT, effective_until TEXT,
            current_version INTEGER NOT NULL DEFAULT 1, created_by TEXT DEFAULT '',
            configuration_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(company_id, policy_key),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS policy_versions (
            policy_version_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, policy_id INTEGER NOT NULL,
            version_number INTEGER NOT NULL, summary TEXT DEFAULT '',
            source_document_id INTEGER, created_by TEXT DEFAULT '', created_at TEXT NOT NULL,
            UNIQUE(company_id, policy_id, version_number),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY(policy_id) REFERENCES policies(policy_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS policy_rules (
            rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, policy_id INTEGER NOT NULL,
            policy_version_id INTEGER, rule_key TEXT NOT NULL, name TEXT NOT NULL,
            description TEXT DEFAULT '', priority TEXT NOT NULL DEFAULT 'medium',
            conditions_json TEXT NOT NULL DEFAULT '{}', actions_json TEXT NOT NULL DEFAULT '{}',
            approval_level TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
            effective_from TEXT, effective_until TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(company_id, policy_id, rule_key),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY(policy_id) REFERENCES policies(policy_id) ON DELETE CASCADE,
            FOREIGN KEY(policy_version_id) REFERENCES policy_versions(policy_version_id) ON DELETE SET NULL)""",

        """CREATE TABLE IF NOT EXISTS documents (
            document_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, title TEXT NOT NULL, filename TEXT NOT NULL,
            document_type TEXT DEFAULT '', storage_path TEXT DEFAULT '', category TEXT DEFAULT '',
            department TEXT DEFAULT '', visibility TEXT NOT NULL DEFAULT 'company',
            status TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
            uploaded_by TEXT DEFAULT '', published_at TEXT, expires_at TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS document_chunks (
            chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, document_id INTEGER NOT NULL, chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL, embedding_ref TEXT DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
            UNIQUE(company_id, document_id, chunk_index),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS document_permissions (
            company_id TEXT NOT NULL, document_id INTEGER NOT NULL,
            role TEXT DEFAULT '', department TEXT DEFAULT '', user_id TEXT DEFAULT '',
            PRIMARY KEY(company_id, document_id, role, department, user_id),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS company_resources (
            resource_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
            description TEXT DEFAULT '', category TEXT DEFAULT '', keywords TEXT DEFAULT '',
            posted_by TEXT DEFAULT '', posted_by_role TEXT DEFAULT '', audience TEXT DEFAULT 'all',
            department TEXT DEFAULT '', priority TEXT NOT NULL DEFAULT 'medium',
            published_at TEXT, expires_at TEXT, status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS company_updates (
            update_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', link_url TEXT NOT NULL DEFAULT '',
            posted_by TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
            priority TEXT NOT NULL DEFAULT 'normal', audience TEXT NOT NULL DEFAULT 'company',
            department TEXT NOT NULL DEFAULT '', published_at TEXT, expires_at TEXT,
            status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS company_update_reads (
            company_id TEXT NOT NULL, update_id INTEGER NOT NULL, user_id TEXT NOT NULL,
            read_at TEXT NOT NULL, PRIMARY KEY(company_id, update_id, user_id),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY(update_id) REFERENCES company_updates(update_id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES company_users(user_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS internal_emails (
            email_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, sender_user_id TEXT NOT NULL,
            subject TEXT NOT NULL, body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft', sent_at TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY(sender_user_id) REFERENCES company_users(user_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS internal_email_recipients (
            company_id TEXT NOT NULL, email_id INTEGER NOT NULL,
            recipient_user_id TEXT NOT NULL, read_at TEXT,
            PRIMARY KEY(company_id,email_id,recipient_user_id),
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY(email_id) REFERENCES internal_emails(email_id) ON DELETE CASCADE,
            FOREIGN KEY(recipient_user_id) REFERENCES company_users(user_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS conversations (
            conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, user_id TEXT NOT NULL, title TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS conversation_messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, conversation_id INTEGER NOT NULL, user_id TEXT DEFAULT '',
            role TEXT NOT NULL, content TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS short_term_memory (
            memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, user_id TEXT NOT NULL, conversation_id INTEGER,
            workflow_id TEXT DEFAULT '', memory_key TEXT NOT NULL,
            memory_value_json TEXT NOT NULL DEFAULT '{}', expires_at TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS long_term_memory (
            memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, user_id TEXT DEFAULT '', memory_type TEXT NOT NULL,
            memory_key TEXT NOT NULL, content TEXT NOT NULL, source_type TEXT DEFAULT '',
            source_id TEXT DEFAULT '', confidence REAL DEFAULT 0.0,
            metadata_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS workflow_requests (
            workflow_id TEXT PRIMARY KEY, company_id TEXT NOT NULL, user_id TEXT NOT NULL,
            request_text TEXT NOT NULL, request_category TEXT DEFAULT '', intent TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'received', decision TEXT DEFAULT '',
            assigned_agents_json TEXT NOT NULL DEFAULT '[]',
            selected_tools_json TEXT NOT NULL DEFAULT '[]',
            context_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS workflow_executions (
            execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, workflow_id TEXT NOT NULL, stage TEXT NOT NULL,
            agent_key TEXT DEFAULT '', tool_key TEXT DEFAULT '',
            input_json TEXT NOT NULL DEFAULT '{}', output_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'started', created_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS approvals (
            approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, workflow_id TEXT NOT NULL, requested_by TEXT NOT NULL,
            approver_user_id TEXT DEFAULT '', approval_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', reason TEXT DEFAULT '',
            requested_at TEXT NOT NULL, decided_at TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",

        """CREATE TABLE IF NOT EXISTS audit_logs (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL, user_id TEXT DEFAULT '', workflow_id TEXT DEFAULT '',
            action TEXT NOT NULL, resource_type TEXT DEFAULT '', resource_id TEXT DEFAULT '',
            details_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(company_id) ON DELETE CASCADE)""",
    ]

    for statement in statements:
        conn.execute(statement)

    policy_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(policies)").fetchall()}
    if "configuration_json" not in policy_columns:
        conn.execute("ALTER TABLE policies ADD COLUMN configuration_json TEXT NOT NULL DEFAULT '{}'")

    for statement in [
        "CREATE INDEX IF NOT EXISTS idx_departments_company ON company_departments(company_id)",
        "CREATE INDEX IF NOT EXISTS idx_roles_company ON company_roles(company_id)",
        "CREATE INDEX IF NOT EXISTS idx_permissions_company ON permissions(company_id)",
        "CREATE INDEX IF NOT EXISTS idx_agents_company ON company_agents(company_id)",
        "CREATE INDEX IF NOT EXISTS idx_tools_company ON company_tools(company_id)",
        "CREATE INDEX IF NOT EXISTS idx_policies_company_status ON policies(company_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_policy_rules_company_policy ON policy_rules(company_id, policy_id)",
        "CREATE INDEX IF NOT EXISTS idx_documents_company_status ON documents(company_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_resources_company_active ON company_resources(company_id, status, published_at, expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_updates_company_active ON company_updates(company_id, status, published_at, expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_emails_company_sender ON internal_emails(company_id, sender_user_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_email_recipients_user ON internal_email_recipients(company_id, recipient_user_id, email_id)",
        "CREATE INDEX IF NOT EXISTS idx_conversations_company_user ON conversations(company_id, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_messages_conversation ON conversation_messages(company_id, conversation_id)",
        "CREATE INDEX IF NOT EXISTS idx_short_memory_user ON short_term_memory(company_id, user_id, conversation_id)",
        "CREATE INDEX IF NOT EXISTS idx_long_memory_company ON long_term_memory(company_id, memory_type, status)",
        "CREATE INDEX IF NOT EXISTS idx_workflows_company_user ON workflow_requests(company_id, user_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_execution_workflow ON workflow_executions(company_id, workflow_id)",
        "CREATE INDEX IF NOT EXISTS idx_approvals_workflow ON approvals(company_id, workflow_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_audit_company_time ON audit_logs(company_id, created_at)",
    ]:
        conn.execute(statement)
