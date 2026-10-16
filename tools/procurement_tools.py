"""Tenant-backed procurement tools."""
from typing import Any, Dict
import re


def _identity(details: Dict[str, Any]):
    from company.store import authorize_user
    company_id = str(details.get("company_id") or "")
    user_id = str(details.get("user_id") or "")
    authorize_user(company_id, user_id)
    return company_id, user_id


def inventory_check(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    company_id, _ = _identity(details)
    from company.catalog_service import list_inventory
    item_type = str(details.get("item_type") or "laptop").strip()
    items = list_inventory(company_id, item_type)
    available = [item for item in items if int(item.get("quantity_available") or 0) > 0]
    return {"status": "success" if items else "not_configured", "executed": False, "action": "Inventory check", "available": bool(available), "available_items": available, "message": f"Found {len(available)} available {item_type} item(s)." if items else f"No {item_type} inventory is configured for this company."}


def hardware_catalog(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    company_id, _ = _identity(details)
    from company.catalog_service import list_inventory
    item_type = str(details.get("item_type") or "laptop").strip()
    products = list_inventory(company_id, item_type)
    return {"status": "success" if products else "not_configured", "executed": False, "item_type": item_type, "products": products, "message": f"Retrieved {len(products)} company catalog item(s)." if products else f"No {item_type} products are configured for this company."}


def vendor_service(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    company_id, _ = _identity(details)
    from company.catalog_service import list_vendors
    vendors = list_vendors(company_id)
    return {"status": "success" if vendors else "not_configured", "executed": False, "vendors": vendors, "message": f"Retrieved {len(vendors)} company vendor(s)." if vendors else "No vendors are configured for this company."}


def purchase_request(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    company_id, user_id = _identity(details)
    from company.catalog_service import list_inventory
    from company.request_service import create_department_request, get_my_department_request, list_my_department_requests
    text = str(message or "")
    request_match = re.search(r"\bPR-[A-Z0-9-]+\b", text, re.IGNORECASE)
    action_words = ("create", "submit", "request", "buy", "purchase")
    if request_match and not any(word in text.lower() for word in action_words):
        record = get_my_department_request(company_id, user_id, request_match.group(0))
        if not record or record.get("service_area") != "Procurement":
            return {"status": "not_found", "executed": False, "message": "That purchase request was not found in your account."}
        return {"status": "success", "executed": False, "record": record, "message": f"Purchase request {record['request_id']} is {record['status'].replace('_', ' ')}."}
    if any(word in text.lower() for word in ("status", "history", "previous", "my purchase requests", "my orders")) and not any(word in text.lower() for word in action_words):
        records = list_my_department_requests(company_id, user_id, "Procurement")
        return {"status": "success" if records else "no_result", "executed": False, "records": records, "message": f"Retrieved {len(records)} procurement request(s)." if records else "No procurement requests were found in your account."}

    item_type = str(details.get("item_type") or "laptop").strip().lower()
    inventory = list_inventory(company_id, item_type)
    model = str(details.get("model") or details.get("item") or "").strip()
    if not model:
        lower_text = text.casefold()
        model = next((item["model"] for item in inventory if item["model"].casefold() in lower_text), "")
    if not model:
        # A model may be inferred only from an unambiguous match to actual
        # inventory specifications; generic requests remain incomplete.
        ignored = {"need", "want", "request", "purchase", "buy", "order", "new", "laptop", "computer", "device", "for", "the", "a", "an", "my", "please", "development"}
        tokens = {word for word in re.findall(r"[a-z0-9]+", text.casefold()) if len(word) > 1 and word not in ignored}
        scored = []
        for candidate in inventory:
            specs = candidate.get("specifications") or {}
            searchable = " ".join([str(candidate.get("model") or ""), *(str(value) for value in specs.values())]).casefold()
            score = len(tokens & set(re.findall(r"[a-z0-9]+", searchable)))
            if score:
                scored.append((score, candidate["model"]))
        if scored:
            best_score = max(score for score, _ in scored)
            best_models = [name for score, name in scored if score == best_score]
            if len(best_models) == 1:
                model = best_models[0]
    if not model:
        return {"status": "missing_information", "executed": False, "request_status": "not_submitted", "item_type": item_type, "message": f"Select a configured {item_type} model before submitting the purchase request."}
    product = next((item for item in inventory if item["model"].casefold() == model.casefold()), None)
    if not product:
        return {"status": "not_found", "executed": False, "request_status": "not_submitted", "item_type": item_type, "model": model, "message": f"The requested model '{model}' is not available in this company's catalog."}
    try:
        quantity = int(details.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 0
    if quantity <= 0:
        return {"status": "invalid", "executed": False, "message": "Purchase quantity must be a positive whole number."}
    if int(product.get("quantity_available") or 0) < quantity:
        return {"status": "out_of_stock", "executed": False, "request_status": "not_submitted", "item_type": item_type, "model": model, "message": f"{model} does not have enough available stock."}
    from company.store import get_company_context
    context = get_company_context(company_id) or {}
    policies = context.get("policies", {})
    rules = context.get("approval_rules", {})
    amount = float(product["unit_price"]) * quantity
    budget = policies.get("laptop_budget_inr") if item_type == "laptop" else policies.get(f"{item_type}_budget_inr")
    if budget is None:
        return {"status": "policy_unavailable", "executed": False, "message": "No procurement budget is configured for this item; no request was submitted."}
    try:
        budget = float(budget)
    except (TypeError, ValueError):
        return {"status": "policy_invalid", "executed": False, "message": "The configured procurement budget is invalid; no request was submitted."}
    if amount > budget:
        return {"status": "budget_exceeded", "executed": False, "requested_amount": amount, "budget_limit": budget, "message": f"The request total {product['currency']} {amount:,.2f} exceeds the configured budget {product['currency']} {budget:,.2f}. No request was created."}
    finance_budget = policies.get("finance_available_budget_inr")
    if finance_budget is None:
        return {"status": "policy_unavailable", "executed": False, "message": "The company Finance budget is not configured, so funding cannot be validated and the purchase request was not created."}
    try:
        finance_budget = float(finance_budget)
    except (TypeError, ValueError):
        return {"status": "policy_invalid", "executed": False, "message": "The configured Finance budget is invalid; no request was created."}
    if amount > finance_budget:
        return {"status": "finance_budget_exceeded", "executed": False, "requested_amount": amount, "finance_budget_limit": finance_budget, "message": f"The request total {product['currency']} {amount:,.2f} exceeds the currently configured Finance budget of {product['currency']} {finance_budget:,.2f}. No request was created."}
    threshold = rules.get("purchase_above_inr")
    if threshold is None:
        requires_approval = True
    else:
        try:
            requires_approval = amount > float(threshold)
        except (TypeError, ValueError):
            return {"status": "policy_invalid", "executed": False, "message": "The configured procurement approval threshold is invalid; no request was submitted."}
    result = create_department_request(company_id=company_id, user_id=user_id, workflow_id=str(details.get("workflow_id") or ""), service_area="Procurement", request_type="purchase_request", title=f"{quantity} x {model}", description=text, amount=amount, currency=str(product["currency"]), details={"inventory_id": product["inventory_id"], "model": model, "item_type": item_type, "quantity": quantity}, requires_approval=requires_approval)
    if not isinstance(result, dict):
        return {"status": "error", "executed": False, "message": "The procurement request could not be recorded."}
    result.update({"tool": "purchase_request", "model": model, "quantity": quantity, "unit_price": product["unit_price"], "requested_amount": amount, "laptop_budget_limit": budget, "finance_budget_available": finance_budget, "finance_budget_check": "passed"})
    return result


def purchase_order(details: Dict[str, Any], message: str):
    details = details if isinstance(details, dict) else {}
    company_id, user_id = _identity(details)
    request_id = str(details.get("request_id") or "").strip()
    if not request_id:
        return {"status": "missing_information", "executed": False, "message": "A purchase request ID is required before a purchase order can be created."}
    from company.request_service import create_purchase_order_from_request
    result = create_purchase_order_from_request(company_id, user_id, str(details.get("workflow_id") or ""), request_id)
    result["tool"] = "purchase_order"
    return result

