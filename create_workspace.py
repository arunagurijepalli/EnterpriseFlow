import getpass
from company.onboarding_service import create_company_workspace

name = input("Company name: ").strip()
email = input("Administrator work email: ").strip().lower()
domain = email.rsplit("@", 1)[-1] if "@" in email else ""
password = getpass.getpass("Create administrator password (minimum 8 characters): ")
confirm = getpass.getpass("Confirm password: ")

if password != confirm:
    raise SystemExit("Passwords do not match. No workspace created.")

try:
    result = create_company_workspace(
        company_name=name,
        admin_name=input("Administrator full name: ").strip(),
        admin_email=email,
        password=password,
        company_domain=domain,
    )
    print("\nWorkspace created successfully.")
    print("Workspace ID:", result["company_id"])
    print("Administrator email:", result["email"])
    print("Company domain:", result["domain"])
except Exception as exc:
    print("\nWorkspace creation failed:", exc)
