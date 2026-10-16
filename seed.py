"""Create the optional local development tenant and sample catalog."""
from company.store import ensure_demo_company, initialize_company_store


if __name__ == "__main__":
    initialize_company_store()
    ensure_demo_company()
    print("Development tenant is ready: demo_company")
    print("Employee: employee@demo.local / Employee@1234")
    print("Admin: admin@demo.local / Admin@1234")
