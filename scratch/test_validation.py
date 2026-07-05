import sys
import os

# Add workspace directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.validation_engine import validate_invoice

def test_validation():
    # 1. Clean invoice
    clean_data = {
        "vendor_name": "ACME Corp",
        "invoice_number": "INV-001",
        "invoice_date": "2026-07-01",
        "due_date": "2026-08-01",
        "line_items": [
            {"description": "Item 1", "quantity": 2, "unit_price": 50, "amount": 100.0},
            {"description": "Item 2", "quantity": 1, "unit_price": 200, "amount": 200.0}
        ],
        "subtotal": 300.0,
        "tax": 30.0,
        "total": 330.0
    }
    res = validate_invoice(clean_data, [])
    assert res["status"] == "approved", f"Expected approved, got {res}"
    assert len(res["flags"]) == 0, f"Expected 0 flags, got {res['flags']}"
    print("Test 1 (Clean Invoice) passed!")

    # 2. Duplicate check
    existing = [
        {"vendor_name": "ACME Corp", "invoice_number": "INV-001"}
    ]
    res = validate_invoice(clean_data, existing)
    assert res["status"] == "needs_review"
    assert any(f["type"] == "duplicate" for f in res["flags"])
    print("Test 2 (Duplicate check) passed!")

    # 3. Math mismatch
    bad_math = clean_data.copy()
    bad_math["total"] = 350.0  # Should be 330
    res = validate_invoice(bad_math, [])
    assert res["status"] == "needs_review"
    assert any(f["type"] == "math_mismatch" for f in res["flags"])
    print("Test 3 (Math mismatch check) passed!")

    # 4. High value
    high_value = clean_data.copy()
    high_value["total"] = 60000.0
    res = validate_invoice(high_value, [])
    assert res["status"] == "needs_review"
    assert any(f["type"] == "high_value" for f in res["flags"])
    print("Test 4 (High value check) passed!")

    # 5. Incomplete fields
    incomplete = clean_data.copy()
    incomplete["vendor_name"] = None
    res = validate_invoice(incomplete, [])
    assert res["status"] == "needs_review"
    assert any(f["type"] == "incomplete" for f in res["flags"])
    print("Test 5 (Incomplete fields check) passed!")

    print("All validation tests passed successfully!")

if __name__ == "__main__":
    test_validation()
