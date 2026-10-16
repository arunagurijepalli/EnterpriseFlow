# EnterpriseFlow

EnterpriseFlow is a tenant-aware workflow application built on Streamlit and SQLite. Each company workspace has its own users, policies, documents, workflows, approvals, notifications, audit events, and company links.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run ui\app.py
```

The application creates database tables on startup, but does not create a company or development login automatically. Use **Create a company workspace** on the sign-in screen to register a tenant and its first administrator.

To create the optional development tenant instead, run:

```powershell
python seed.py
```

The development credentials are printed by the seed command. Do not use them for a production deployment. Set `COMPANY_DB_PATH` to select a persistent database location, and provide provider credentials through environment variables or a local `.env` file.

## HR and IT service catalogue

See [SERVICE_CATALOG.md](SERVICE_CATALOG.md) for the HR and IT request categories, routing behavior, confirmation/approval expectations, Admin Service Desk queues, and integration boundaries. Employees can submit supported requests in natural language; informational questions are read-only, while write actions require confirmation and may require administrator approval. Company administrators should configure allowed leave types in the policy settings before employees submit special leave types.

A request tracked by EnterpriseFlow is not automatically a completed external operation. Password resets, MDM enrollment, backup recovery, system upgrades, payroll processing, insurance/visa submissions, and similar operations require the relevant provider integration or authorized staff processing. The app should report such requests as tracked/pending rather than claim an unconfigured external action succeeded. Anonymous whistleblower intake is not currently supported.

## Employee and administrator workspace (v6 UI update)

`UPGRADE_NOTES_v6.md` documents the updated role-based navigation, employee/admin profile pages with saved profile photos, employee project-folder submission and administrator review queue, and tenant-scoped two-way document exchange. Employees no longer see standalone Emails or Company Policies entries in the sidebar; the policy configuration remains in the Admin Console for the coordinator's policy checks. Company knowledge documents remain accessible through the Documents page.

Project submissions and document exchanges are saved to SQLite or the scoped project-file directory, then shown in the Admin Console with preview/download and status/feedback controls. Upload limits and tenant/role access checks are enforced by the service layer. Office formats that cannot be previewed inline can be downloaded and opened in their native application.

## Verification

```powershell
python -m unittest discover -s tests -v
python -m compileall -q company core agents tools ui seed.py tests
```

The current implementation persists company onboarding, password-based authentication, tenant-scoped role checks, employee and department records, workflow requests, approval decisions, internal email, announcements, shared links, documents, notifications, and audit events. Procurement uses each tenant's configured inventory and policy values. If an external system such as an email provider, attendance source, payroll system, or recruiting directory is not configured, the corresponding feature reports that state instead of inventing records.

SQLite is used for local demonstration and development. For production use, deploy behind HTTPS with managed secret storage, backups, monitoring, and an operational database migration plan.


## Login database path note (v7)

The store loads this project's `.env` before computing its database path. Relative `COMPANY_DB_PATH` values are anchored to the project root. Keep your existing `.env` and `data/company.db` when updating.

## v8 workspace, approvals and admin-defaults update

See `UPGRADE_NOTES_v8.md` for the changes to employee pending-request retrieval, legacy approval reconciliation, department-routed approval notifications, editable company profile/laptop catalogue defaults, role-specific navigation, profile photos, project submissions, two-way document exchange, and the UI palette. The source archive intentionally omits `.env`, SQLite database files and user uploads.


## UI v9 full pastel theme
The full Streamlit workspace uses the blue, light-pink, light-orange and sky-blue pastel palette across all role pages, navigation, forms, buttons, tabs, approvals, profile, project and document views. See `UPGRADE_NOTES_v9.md`.

## AI provider outage behavior (v10)

When a configured LLM provider returns a rate limit or transient outage, the
coordinator now applies a bounded per-provider timeout and a temporary circuit
breaker. Subsequent workflow stages skip the same failed provider during its
cooldown and use deterministic, permission-safe fallback behavior. See
`UPGRADE_NOTES_v10.md`. This does not extend API quota or replace external provider
availability; it only avoids repeatedly waiting for providers known to be down.

## v11 conversation-context recovery

v11 fixes a conversation routing issue where a fresh IT request (for example, a Wi-Fi issue) could be concatenated into a pending leave-date clarification. It detects clear topic switches and removes the stale clarification pair from the analysis history. Numeric leave dates separated by commas are accepted. “My pending approvals” is answered from tenant-scoped saved employee requests or the authorized approval queue, without relying on the LLM. Simple greetings are answered locally.

See `UPGRADE_NOTES_v11.md`. Replace source files only and preserve `.env`, the SQLite database, and uploaded files.


## v12: acceptance coverage and approval-history recovery
See `UPGRADE_NOTES_v12.md`. The deterministic catalogue covers the supplied HR/IT acceptance prompts, pending employee views include workflow-only records, legacy workflow approvals are reconciled to the company/admin queue idempotently, and demo laptop specs are editable planning baselines that preserve administrator changes. External service execution still depends on authorized provider integrations.

## v13 AI Coordinator routing and state recovery

See [UPGRADE_NOTES_v13.md](UPGRADE_NOTES_v13.md) for deterministic HR/IT routing, explicit IT-ticket intent handling, saved-ticket follow-ups, confirmed leave action continuation, read-only HR record lookups, clarification-state guards, pending-approval/clarification separation, and filtering of legacy read-only/command false positives. Run the full suite in the active Windows `.venv312` before treating the entire integration stack as verified. Update source files only and preserve the active `.env`, company database, uploads, and virtual environment.
