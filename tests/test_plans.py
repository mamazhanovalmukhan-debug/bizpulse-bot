"""Тесты тарифной системы."""
import sys
sys.path.insert(0, "/tmp/bp2/app")

from services.plan_service import (
    PLANS, PLAN_ORDER, location_limit_message, plan_list_text
)

def test_plans_exist():
    for code in ["START", "GROW", "NETWORK", "ENTERPRISE"]:
        assert code in PLANS, f"Plan {code} missing"

def test_start_has_1_location():
    assert PLANS["START"]["max_locations"] == 1

def test_grow_has_5_locations():
    assert PLANS["GROW"]["max_locations"] == 5

def test_network_has_15_locations():
    assert PLANS["NETWORK"]["max_locations"] == 15

def test_enterprise_no_limit():
    assert PLANS["ENTERPRISE"]["max_locations"] is None

def test_plan_prices():
    assert PLANS["START"]["price"] == 199000
    assert PLANS["GROW"]["price"] == 349000
    assert PLANS["NETWORK"]["price"] == 599000
    assert PLANS["ENTERPRISE"]["price"] == 0

def test_plan_order_is_ascending():
    prices = [PLANS[c]["price"] for c in PLAN_ORDER if PLANS[c]["price"] > 0]
    assert prices == sorted(prices), "Prices not ascending"

def test_location_limit_message_contains_plan():
    check = {"ok": False, "current": 1, "limit": 1,
              "plan_code": "START", "next_plan": PLANS["GROW"]}
    msg = location_limit_message(check)
    assert "Старт" in msg or "START" in msg
    assert "Рост" in msg or "GROW" in msg

def test_plan_list_not_empty():
    text = plan_list_text()
    assert len(text) > 50

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
    print(f"\nPlan tests: {passed} passed, {failed} failed")
