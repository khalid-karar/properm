from .models import AuditLog, Outbox


def log(db, actor_id, action, entity, entity_id=None, detail=None):
    db.add(AuditLog(actor_id=actor_id, action=action, entity=entity, entity_id=entity_id, detail=detail or {}))


def emit(db, event, payload=None):
    """Write an event to the transactional outbox in the same transaction as the change."""
    db.add(Outbox(event=event, payload=payload or {}))
