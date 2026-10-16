# Company / Tenant Layer — Enterprise Workflow Platform

This increment adds a tenant-aware company context without rebuilding the existing Module 2 tools/workflow.

## What was added

- `company/store.py`: SQLite persistence for companies and company users.
- `company/context.py`: tenant lookup and backend user/company isolation check.
- `company/admin.py`: company registration and admin-only update helpers.
- `core/state.py`: `company_id`, `user_id`, `user_role`, and tenant context fields.
- `core/workflow.py`: loads tenant context and passes it to AI + tools. The public workflow result does not return the full private company context.
- `core/llm.py`: company context is supplied as current, tenant-scoped grounding data.
- `ui/app.py`: development-only tenant/user inputs for testing. Production login/session must provide verified identity values.

## Demo tenant

On first run, the application creates:

- Company: `demo_company`
- Admin: `demo_admin`
- Employee: `demo_employee`

The demo company includes an example laptop budget of ₹1,20,000 and a purchase approval threshold of ₹1,00,000. These are demo values stored in SQLite and can be updated through the admin API/helpers.

## Test from Python

```python
from core.workflow import run_workflow

result = run_workflow(
    "What is our current laptop budget policy?",
    company_id="demo_company",
    user_id="demo_employee",
)

print(result["response"])
print(result["company_id"])
```

## Update company information

```python
from company.admin import update_company_as_admin

update_company_as_admin(
    company_id="demo_company",
    admin_user_id="demo_admin",
    context_updates={
        "policies": {
            "laptop_budget_inr": 150000,
        }
    },
)
```

After the update, new workflow requests load the latest stored company context.

## Important security boundary

This is the tenant-context foundation, not a complete production authentication system. The next security increment should replace UI text inputs with verified login/session/JWT identity, enforce role-based permissions for company administration, and enforce per-agent/per-tool authorization at the backend before tool execution.
