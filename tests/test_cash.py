"""Тесты кассовой логики."""
import sys
sys.path.insert(0, "/tmp/bp2/app")

from services.cash_service import (
    calc_expected_cash, validate_cash_report,
    check_discrepancy, format_cash_summary
)

def test_calc_expected_basic():
    result = calc_expected_cash(5000, 3000)
    assert result == 8000, f"Expected 8000, got {result}"

def test_calc_expected_with_expenses():
    result = calc_expected_cash(5000, 3000, expenses=500)
    assert result == 7500, f"Expected 7500, got {result}"

def test_calc_expected_with_collection():
    result = calc_expected_cash(5000, 3000, collection=2000)
    assert result == 6000, f"Expected 6000, got {result}"

def test_calc_full_formula():
    # cash_start=5000 + cash_sales=3000 - expenses=500 - refunds=100 - collection=1000 + deposits=200
    result = calc_expected_cash(5000, 3000, expenses=500, refunds=100, collection=1000, deposits=200)
    assert result == 6600, f"Expected 6600, got {result}"

def test_validate_cash_no_errors():
    errors = validate_cash_report(5000, cash_sales=2000)
    assert errors == [], f"Unexpected errors: {errors}"

def test_validate_cash_negative_actual():
    errors = validate_cash_report(5000, cash_actual=-100)
    assert len(errors) > 0, "Expected error for negative cash"

def test_validate_expense_too_large():
    errors = validate_cash_report(1000, expenses=5000)
    assert len(errors) > 0, "Expected error for expense > available"

def test_validate_no_movements_less_than_start():
    errors = validate_cash_report(5000, cash_actual=4000)
    assert len(errors) > 0, "Expected error: actual < start with no movements"

def test_discrepancy_ok():
    result = check_discrepancy(5000, 5005)  # diff = 5, в допуске
    assert result["status"] in ("ok", "warning"), f"Got {result['status']}"

def test_discrepancy_alert():
    result = check_discrepancy(5000, 4000)  # diff = -1000
    assert result["status"] == "alert", f"Got {result['status']}"
    assert result["diff"] == -1000

def test_discrepancy_surplus():
    result = check_discrepancy(5000, 6000)  # diff = +1000
    assert result["status"] == "alert"
    assert result["diff"] == 1000

def test_format_summary_no_crash():
    text = format_cash_summary(5000, 3000, 2000, 1000, 500, 100, 0, 0, 10400, 10500)
    assert "5" in text  # хоть что-то вернулось

if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: EXCEPTION {e}")
            failed += 1
    print(f"\nCash tests: {passed} passed, {failed} failed")
