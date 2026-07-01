"""Централизованная валидация пользовательского ввода."""
from config import config

class ValidationError(Exception):
    """Ошибка валидации с пользовательским сообщением."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def validate_money(text: str, field_name: str = "Сумма",
                   allow_zero: bool = True) -> float:
    """Парсит и валидирует денежную сумму."""
    if not text or not text.strip():
        raise ValidationError(f"{field_name}: введите число.")
    cleaned = text.replace(" ", "").replace(",", ".").strip()
    try:
        val = float(cleaned)
    except ValueError:
        raise ValidationError(f"{field_name}: введите число, например: 5000")
    if val < 0:
        raise ValidationError(f"{field_name} не может быть отрицательным.")
    if not allow_zero and val == 0:
        raise ValidationError(f"{field_name} должна быть больше нуля.")
    if val > config.CASH_MAX_AMOUNT:
        raise ValidationError(
            f"{field_name}: слишком большая сумма ({val:,.0f} ₽). "
            f"Максимум: {config.CASH_MAX_AMOUNT:,.0f} ₽. Проверьте данные."
        )
    return val


def validate_name(text: str, field_name: str = "Название",
                  min_len: int = 2) -> str:
    """Валидирует текстовое название."""
    if not text or not text.strip():
        raise ValidationError(f"{field_name}: введите текст.")
    text = text.strip()
    if len(text) < min_len:
        raise ValidationError(f"{field_name}: минимум {min_len} символа.")
    if len(text) > config.MAX_NAME_LENGTH:
        raise ValidationError(
            f"{field_name}: слишком длинное (максимум {config.MAX_NAME_LENGTH} символов)."
        )
    return text


def validate_person_name(text: str) -> str:
    """Валидирует имя человека — должно содержать буквы."""
    name = validate_name(text, "Имя")
    if not any(c.isalpha() for c in name):
        raise ValidationError("Имя должно содержать буквы.")
    return name


def validate_hour(text: str) -> int:
    """Валидирует час (0-23)."""
    try:
        h = int(text.strip())
        if not 0 <= h <= 23:
            raise ValueError
        return h
    except ValueError:
        raise ValidationError("Введите час от 0 до 23 (например: 9 или 21).")


def validate_quantity(text: str, field_name: str = "Количество") -> float:
    """Валидирует количество товара."""
    cleaned = text.replace(",", ".").strip()
    try:
        val = float(cleaned)
    except ValueError:
        raise ValidationError(f"{field_name}: введите число, например: 10.5")
    if val < 0:
        raise ValidationError(f"{field_name} не может быть отрицательным.")
    if val > 1_000_000:
        raise ValidationError(f"{field_name}: слишком большое значение.")
    return val


def validate_comment(text: str, optional: bool = True) -> str:
    """Валидирует комментарий."""
    if not text or text.strip() in ("Пропустить", "Нет", "0"):
        return ""
    text = text.strip()
    if len(text) > config.MAX_COMMENT_LENGTH:
        return text[:config.MAX_COMMENT_LENGTH]
    return text


def validate_count(text: str, min_val: int = 1, max_val: int = 100) -> int:
    """Валидирует целое число в диапазоне."""
    try:
        val = int(text.strip())
        if not min_val <= val <= max_val:
            raise ValueError
        return val
    except ValueError:
        raise ValidationError(f"Введите число от {min_val} до {max_val}.")
