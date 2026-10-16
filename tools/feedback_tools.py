"""Authenticated self-service access to published performance feedback."""
from company.employee_portfolio_service import get_my_published_performance


def my_performance_feedback(details, message=""):
    details = details if isinstance(details, dict) else {}
    company_id = str(details.get("company_id") or "").strip()
    user_id = str(details.get("user_id") or "").strip()
    if not company_id or not user_id:
        return {"status": "error", "message": "Authenticated employee context is required."}
    try:
        reviews = get_my_published_performance(company_id, user_id)
    except (PermissionError, ValueError):
        return {"status": "error", "message": "Feedback is unavailable for this account."}
    if not reviews:
        return {"status": "success", "message": "No performance feedback is available yet.", "feedback": []}
    safe_reviews = [{k: row.get(k) for k in ("review_period", "rating", "strengths", "achievements_summary", "areas_for_improvement", "goals", "manager_feedback", "feedback_comments", "created_at", "status")} for row in reviews]
    return {"status": "success", "message": "Published performance feedback for the authenticated employee.", "feedback": safe_reviews, "note": "The stored fields are HR feedback. Any AI-generated summary or recommendations must be clearly identified as AI-generated."}
