from __future__ import annotations

from typing import Any, Dict, List

from company.policy_service import get_policy_rules


def _compare(left: Any, operator: str, right: Any) -> bool:
    """Evaluate one comparison."""

    try:
        if operator == ">":
            return left > right

        if operator == ">=":
            return left >= right

        if operator == "<":
            return left < right

        if operator == "<=":
            return left <= right

        if operator in ("=", "=="):
            return left == right

        if operator in ("!=", "<>"):
            return left != right

    except (TypeError, ValueError):
        return False

    return False


def _evaluate_conditions(
    conditions: Dict[str, Any],
    context: Dict[str, Any],
) -> bool:
    """Evaluate policy conditions against workflow context."""

    for key, expected_value in conditions.items():

        # Skip operator metadata.
        if key.endswith("_operator"):
            continue

        actual_value = context.get(key)

        if actual_value is None:
            return False

        # Policy format:
        # amount_inr + amount_operator
        # annual_leave_days + annual_leave_days_operator
        #
        # For amount_inr specifically, the database stores
        # the operator as amount_operator.
        if key == "amount_inr":
            operator = conditions.get(
                "amount_operator",
                "==",
            )
        else:
            operator = conditions.get(
                f"{key}_operator",
                "==",
            )

        if not _compare(
            actual_value,
            operator,
            expected_value,
        ):
            return False

    return True


def evaluate_policy_rules(
    company_id: str,
    department: str | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Evaluate active company policy rules against workflow data.

    Policy conditions are evaluated by deterministic code.
    The LLM does not make authorization decisions.
    """

    context = context or {}

    rules = get_policy_rules(
        company_id=company_id,
        department=department,
    )

    matched_rules: List[Dict[str, Any]] = []
    triggered_actions: Dict[str, Any] = {}

    for rule in rules:

        conditions = rule.get("conditions") or {}

        # An empty condition set means the rule is
        # unconditional and should always match.
        if conditions:
            if not _evaluate_conditions(
                conditions,
                context,
            ):
                continue

        actions = rule.get("actions") or {}

        matched_rules.append(
            {
                "policy_key": rule.get("policy_key"),
                "policy_name": rule.get("policy_name"),
                "rule_key": rule.get("rule_key"),
                "rule_name": rule.get("rule_name"),
                "conditions": conditions,
                "actions": actions,
                "approval_level": rule.get("approval_level"),
                "priority": rule.get("priority"),
                "risk_level": rule.get("risk_level"),
            }
        )

        triggered_actions.update(actions)

    return {
        "policy_evaluated": True,
        "matched_rules": matched_rules,
        "actions": triggered_actions,
        "approval_required": bool(
            triggered_actions.get(
                "approval_required",
                False,
            )
            or triggered_actions.get(
                "manager_approval_required",
                False,
            )
        ),
    }