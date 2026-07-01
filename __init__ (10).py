"""Audit log — запись всех значимых действий."""
import logging
import json
from database.session import get_pool

log = logging.getLogger(__name__)

async def log_action(business_id: int, user_id: int, action: str,
                     entity_type: str = "", entity_id: int = None,
                     old_value: dict = None, new_value: dict = None):
    """Записать действие в audit_logs. Никогда не бросает исключение."""
    try:
        await get_pool().execute(
            """INSERT INTO audit_logs
               (business_id,user_id,action,entity_type,entity_id,
                old_value,new_value)
               VALUES ($1,$2,$3,$4,$5,$6,$7)""",
            business_id, user_id, action, entity_type, entity_id,
            json.dumps(old_value, default=str) if old_value else None,
            json.dumps(new_value, default=str) if new_value else None,
        )
    except Exception as e:
        log.error(f"audit_log error ({action}): {e}")

async def get_audit_log(business_id: int, limit: int = 50) -> list:
    try:
        rows = await get_pool().fetch(
            """SELECT al.*,u.full_name FROM audit_logs al
               LEFT JOIN users u ON u.telegram_id=al.user_id
               WHERE al.business_id=$1
               ORDER BY al.created_at DESC LIMIT $2""",
            business_id, limit
        )
        return [dict(r) for r in rows]
    except Exception as e:
        log.error(f"get_audit_log error: {e}")
        return []

# Константы действий
BUSINESS_CREATED      = "business_created"
PLAN_CHANGED          = "plan_changed"
PAYMENT_RECEIVED      = "payment_received"
SUBSCRIPTION_EXTENDED = "subscription_extended"
BUSINESS_BLOCKED      = "business_blocked"
SHIFT_OPENED          = "shift_opened"
SHIFT_CLOSED          = "shift_closed"
CASH_EXPENSE          = "cash_expense"
CASH_COLLECTION       = "cash_collection"
CASH_DISCREPANCY      = "cash_discrepancy"
DELIVERY_RECEIVED     = "delivery_received"
INVENTORY_COMPLETED   = "inventory_completed"
STOCK_CHANGED         = "stock_changed"
TICKET_CREATED        = "ticket_created"
TICKET_CLOSED         = "ticket_closed"
