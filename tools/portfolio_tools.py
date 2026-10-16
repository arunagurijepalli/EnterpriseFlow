from typing import Any, Dict

from company.employee_portfolio_service import (
    list_projects,
    get_project,
    list_project_modules,
    list_milestones,
    list_achievements,
    list_participations,
    get_performance,
    list_project_files,
)


def employee_portfolio_service(
    details: Dict[str, Any],
    message: str = "",
):
    """
    Read-only employee portfolio tool.

    Uses the authenticated company_id and employee_id from
    workflow details so employees can only access their own
    portfolio data.
    """

    details = details or {}

    company_id = details.get("company_id", "")
    employee_id = (
        details.get("employee_id")
        or details.get("user_id")
        or ""
    )

    if not company_id:
        return {
            "status": "error",
            "message": "Company context is missing.",
        }

    if not employee_id:
        return {
            "status": "error",
            "message": "Employee identity is missing.",
        }

    projects_result = list_projects(
        company_id=company_id,
        employee_id=employee_id,
    )

    if isinstance(projects_result, dict):
        projects = projects_result.get("projects", [])
    else:
        projects = projects_result or []

    if not projects:
        return {
            "status": "success",
            "message": "No projects found for the logged-in employee.",
            "projects": [],
        }

    # --------------------------------------------------------
    # Determine whether the user mentioned a project name
    # --------------------------------------------------------

    message_lower = str(message or "").lower()

    selected_project = None

    for project in projects:
        project_name = str(
            project.get("project_name", "")
        ).strip()

        if project_name and project_name.lower() in message_lower:
            selected_project = project
            break

    # --------------------------------------------------------
    # If no project was explicitly selected
    # --------------------------------------------------------

    if selected_project is None:

        if len(projects) > 1:

            return {
                "status": "success",
                "multiple_projects": True,
                "projects": projects,
                "message": (
                    "The employee has multiple projects. "
                    "Ask the employee which project they want "
                    "to view."
                ),
            }

        selected_project = projects[0]

    project_id = selected_project.get("id")

    if project_id is None:
        project_id = selected_project.get("project_id")

    if project_id is None:
        return {
            "status": "error",
            "message": "Project ID is missing.",
        }

    # --------------------------------------------------------
    # Complete project information
    # --------------------------------------------------------

    project_details = get_project(
        company_id=company_id,
        employee_id=employee_id,
        project_id=project_id,
    )

    modules = list_project_modules(
        company_id=company_id,
        employee_id=employee_id,
        project_id=project_id,
    )

    milestones = list_milestones(
        company_id=company_id,
        employee_id=employee_id,
        project_id=project_id,
    )

    files = list_project_files(
        company_id=company_id,
        employee_id=employee_id,
        project_id=project_id,
    )

    achievements = list_achievements(
        company_id=company_id,
        employee_id=employee_id,
    )

    participations = list_participations(
        company_id=company_id,
        employee_id=employee_id,
    )

    performance = get_performance(
        company_id=company_id,
        employee_id=employee_id,
    )

    return {
        "status": "success",
        "multiple_projects": False,
        "project": project_details,
        "modules": modules,
        "milestones": milestones,
        "achievements": achievements,
        "participations": participations,
        "performance": performance,
        "files": files,
        "message": (
            f"Retrieved portfolio details for "
            f"{selected_project.get('project_name', 'the selected project')}."
        ),
    }
