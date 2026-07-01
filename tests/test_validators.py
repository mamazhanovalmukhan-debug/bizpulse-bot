"""Тесты валидаторов."""
import sys
sys.path.insert(0, "/tmp/bp2/app")

from utils.validators import (
    validate_money, validate_name, validate_person_name,
    validate_hour, validate_quantity, validate_comment,
    ValidationError
)

def test_valid_money():
    assert validate_money("5000") == 5000.0
    assert validate_money("1 500") == 1500.0
    assert validate_money("1,5") == 1.5

def test_money_negative():
    try:
        validate_money("-100")
        assert False, "Should raise"
    except ValidationError:
        pass

def test_money_too_large():
    try:
        validate_money("999999999")
        assert False, "Should raise"
    except ValidationError:
        pass

def test_money_empty():
    try:
        validate_money("")
        assert False, "Should raise"
    except ValidationError:
        pass

def test_valid_name():
    assert validate_name("Кофейня Утро") == "Кофейня Утро"

def test_name_too_short():
    try:
        validate_name("A")
        assert False, "Should raise"
    except ValidationError:
        pass

def test_valid_hour():
    assert validate_hour("9") == 9
    assert validate_hour("21") == 21

def test_invalid_hour():
    for h in ["-1", "25", "abc"]:
        try:
            validate_hour(h)
            assert False, f"Should raise for {h}"
        except ValidationError:
            pass

def test_quantity_valid():
    assert validate_quantity("10") == 10.0
    assert validate_quantity("0.5") == 0.5

def test_quantity_negative():
    try:
        validate_quantity("-1")
        assert False
    except ValidationError:
        pass

def test_comment_skip():
    assert validate_comment("Пропустить") == ""
    assert validate_comment("0") == ""
    assert validate_comment("") == ""

def test_comment_normal():
    assert validate_comment("Хорошая смена") == "Хорошая смена"

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
    print(f"\nValidator tests: {passed} passed, {failed} failed")
