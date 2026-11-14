"""Queue engine: token issuance, fair ordering, atomic advancement and ETA."""
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .models import Counter, Queue, QueueEvent, Service, Token, TokenStatus, utcnow
from .security import new_code

ETA_MIN_SAMPLES = 3  # below this many completed services we fall back to the configured average

TRANSITIONS = {
    "hold": ({TokenStatus.WAITING}, TokenStatus.HELD),
    "resume": ({TokenStatus.HELD}, TokenStatus.WAITING),
    "cancel": ({TokenStatus.WAITING, TokenStatus.HELD}, TokenStatus.CANCELLED),
    "complete": ({TokenStatus.CALLED}, TokenStatus.COMPLETED),
    "no_show": ({TokenStatus.CALLED}, TokenStatus.NO_SHOW),
}


class QueueError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def _lock_queue(db: Session, queue_id: int) -> Queue:
    # A no-op UPDATE takes the row lock on PostgreSQL and the write lock on SQLite,
    # so every queue mutation below is serialised per queue.
    db.execute(
        update(Queue).where(Queue.id == queue_id).values(last_number=Queue.last_number)
        .execution_options(synchronize_session=False)
    )
    queue = db.scalar(select(Queue).where(Queue.id == queue_id).execution_options(populate_existing=True))
    if queue is None:
        raise QueueError("Queue not found", 404)
    return queue


def _event(db: Session, token: Token, action: str, counter_id: int | None = None) -> None:
    db.add(QueueEvent(queue_id=token.queue_id, token_id=token.id, counter_id=counter_id,
                      action=action, created_at=utcnow()))


def _count(db: Session, *criteria) -> int:
    return db.scalar(select(func.count(Token.id)).where(*criteria)) or 0


def _serving_numbers(db: Session, queue_id: int) -> list[int]:
    return list(db.scalars(select(Token.number).where(
        Token.queue_id == queue_id, Token.status == TokenStatus.CALLED).order_by(Token.number)))


def issue_token(db: Session, queue_id: int, customer_name: str | None = None) -> Token:
    queue = _lock_queue(db, queue_id)
    if not queue.is_open:
        raise QueueError("This queue is closed right now")
    queue.last_number += 1
    token = Token(queue_id=queue.id, number=queue.last_number, public_code=new_code(),
                  customer_name=(customer_name or "").strip()[:80] or None,
                  status=TokenStatus.WAITING, created_at=utcnow())
    db.add(token)
    db.flush()
    _event(db, token, "joined")
    db.commit()
    return token


def call_next(db: Session, queue_id: int, counter_id: int) -> Token:
    queue = _lock_queue(db, queue_id)
    counter = db.scalar(select(Counter).where(Counter.id == counter_id, Counter.queue_id == queue.id))
    if counter is None:
        raise QueueError("Counter not found", 404)
    if not counter.is_open:
        raise QueueError("This counter is closed")
    if db.scalar(select(Token.id).where(Token.counter_id == counter.id, Token.status == TokenStatus.CALLED)):
        raise QueueError("This counter is still serving a customer")
    token = db.scalar(select(Token).where(Token.queue_id == queue.id, Token.status == TokenStatus.WAITING)
                      .order_by(Token.number).limit(1))
    if token is None:
        raise QueueError("No customers are waiting", 404)
    token.status = TokenStatus.CALLED
    token.counter_id = counter.id
    token.called_at = utcnow()
    _event(db, token, "called", counter.id)
    db.commit()
    return token


def _locked_token(db: Session, token_id: int, business_id: int | None) -> tuple[Token, Queue]:
    token = db.get(Token, token_id)
    if token is None:
        raise QueueError("Token not found", 404)
    queue = _lock_queue(db, token.queue_id)
    if business_id is not None and queue.business_id != business_id:
        raise QueueError("Token not found", 404)  # never reveal another business's tokens
    db.refresh(token)
    return token, queue


def transition(db: Session, token_id: int, action: str, business_id: int | None = None) -> Token:
    allowed, new_status = TRANSITIONS[action]
    token, _ = _locked_token(db, token_id, business_id)
    if token.status not in allowed:
        raise QueueError(f"Cannot {action.replace('_', ' ')} a token that is {token.status.value}")
    token.status = new_status
    if action == "complete":
        token.completed_at = utcnow()
    _event(db, token, action)
    db.commit()
    return token


def average_service_seconds(db: Session, queue: Queue) -> float:
    service = db.get(Service, queue.service_id)
    rows = db.execute(
        select(Token.called_at, Token.completed_at)
        .where(Token.queue_id == queue.id, Token.status == TokenStatus.COMPLETED,
               Token.called_at.is_not(None), Token.completed_at.is_not(None))
        .order_by(Token.completed_at.desc()).limit(50)
    ).all()
    durations = [(done - start).total_seconds() for start, done in rows if done > start]
    if len(durations) >= ETA_MIN_SAMPLES:
        return sum(durations) / len(durations)
    return float(service.avg_service_seconds)


def estimate_wait_seconds(db: Session, queue: Queue, ahead: int) -> int:
    """Approximate wait: work ahead (waiting + being served) spread across open counters."""
    serving = _count(db, Token.queue_id == queue.id, Token.status == TokenStatus.CALLED)
    open_counters = db.scalar(select(func.count(Counter.id)).where(
        Counter.queue_id == queue.id, Counter.is_open.is_(True))) or 0
    return round((ahead + serving) * average_service_seconds(db, queue) / max(open_counters, 1))


def queue_status(db: Session, queue: Queue) -> dict:
    waiting = _count(db, Token.queue_id == queue.id, Token.status == TokenStatus.WAITING)
    return {
        "queue_name": queue.name,
        "is_open": queue.is_open,
        "now_serving": _serving_numbers(db, queue.id),
        "waiting": waiting,
        "estimated_wait_seconds": estimate_wait_seconds(db, queue, waiting),
    }


def token_view(db: Session, token: Token) -> dict:
    queue = db.get(Queue, token.queue_id)
    position = eta = None
    if token.status == TokenStatus.WAITING:
        ahead = _count(db, Token.queue_id == queue.id, Token.status == TokenStatus.WAITING,
                       Token.number < token.number)
        position, eta = ahead + 1, estimate_wait_seconds(db, queue, ahead)
    return {
        "token_code": token.public_code,
        "number": token.number,
        "status": token.status.value,
        "position": position,
        "estimated_wait_seconds": eta,
        "now_serving": _serving_numbers(db, queue.id),
        "queue_name": queue.name,
    }
