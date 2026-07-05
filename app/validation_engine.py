def validate_invoice(data: dict, existing_invoices: list, threshold: float = 50000.0) -> dict:
    """
    Deterministic rule-based validation engine for invoices.
    
    Checks for:
    1. Duplicate (same vendor + invoice number in existing invoices)
    2. Math mismatch (sum of line items + tax != total, within 1.0 tolerance)
    3. High-value threshold (total > threshold)
    4. Missing required fields (vendor_name, invoice_number, total)
    """
    flags = []

    # Helper to resolve fields from dictionary or SQLAlchemy model
    def get_val(obj, field_name):
        if isinstance(obj, dict):
            return obj.get(field_name)
        return getattr(obj, field_name, None)

    # 1. Duplicate check
    vendor_name = data.get("vendor_name")
    invoice_number = data.get("invoice_number")
    
    if vendor_name and invoice_number:
        for inv in existing_invoices:
            inv_vendor = get_val(inv, "vendor_name")
            inv_number = get_val(inv, "invoice_number")
            if inv_vendor == vendor_name and inv_number == invoice_number:
                flags.append({
                    "type": "duplicate", 
                    "detail": f"Matches an existing invoice in the database (Vendor: {vendor_name}, Inv #: {invoice_number})"
                })
                break

    # 2. Math mismatch check
    line_items = data.get("line_items") or []
    # If line items are objects/dicts, sum their amounts
    line_total = 0.0
    for item in line_items:
        amount = get_val(item, "amount")
        # Handle cases where amount is None or unreadable
        if amount is not None:
            try:
                line_total += float(amount)
            except (ValueError, TypeError):
                pass

    tax = 0.0
    if data.get("tax") is not None:
        try:
            tax = float(data.get("tax"))
        except (ValueError, TypeError):
            pass

    total = 0.0
    if data.get("total") is not None:
        try:
            total = float(data.get("total"))
        except (ValueError, TypeError):
            pass

    expected_total = line_total + tax
    # Tolerance threshold of $1.00
    if abs(expected_total - total) > 1.0:
        flags.append({
            "type": "math_mismatch", 
            "detail": f"Line items sum ({line_total:.2f}) + tax ({tax:.2f}) = {expected_total:.2f}, but invoice total = {total:.2f}"
        })

    # 3. High-value threshold check
    if total and total > threshold:
        flags.append({
            "type": "high_value", 
            "detail": f"Total {total:.2f} exceeds review threshold of {threshold:.2f}"
        })

    # 4. Missing required fields check
    required_fields = ["vendor_name", "invoice_number", "total"]
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        flags.append({
            "type": "incomplete", 
            "detail": f"Missing required fields: {', '.join(missing)}"
        })

    return {
        "flags": flags, 
        "status": "needs_review" if flags else "approved"
    }
