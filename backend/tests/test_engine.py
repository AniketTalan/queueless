import threading
from datetime import timedelta

import pytest

from app import engine as qe
from app.database import SessionLocal
from app.models import Business, Counter, Queue, Service, TokenStatus
from app.security import hash_key, new_api_key, new_code


def _setup(db, counters=1):
    business = Business(name="Clinic", api_key_hash=hash_key(new_api_key()))
    db.add(business)
    db.flush()
    service = Service(business_id=business.id, name="OPD", avg_service_seconds=300)
    db.add(service)
    db.flush()
    queue = Queue(business_id=business.id, service_id=service.id, name="Dr. A", public_code=new_code())
    db.add(queue)
    db.flush()
    counter_list = [Counter(queue_id=queue.id, name=f"Room {i}") for i in range(counters)]
    db.add_all(counter_list)
    db.commit()
    return business, queue, counter_list


def test_concurrent_token_issuance_is_unique_and_gapless():
    db = SessionLocal()
    _, queue, _ = _setup(db)
    queue_id = queue.id
    db.close()
    numbers, errors, lock = [], [], threading.Lock()

    def worker():
        session = SessionLocal()
        try:
            token = qe.issue_token(session, queue_id)
            with lock:
                numbers.append(token.number)
        except Exception as exc:  # collected and asserted below
            with lock:
                errors.append(repr(exc))
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sorted(numbers) == list(range(1, 21))


def test_fair_order_with_hold_resume_and_cancel():
    db = SessionLocal()
    _, queue, (counter,) = _setup(db)
    t1, t2, t3, _t4 = (qe.issue_token(db, queue.id) for _ in range(4))
    qe.transition(db, t1.id, "hold")
    assert qe.call_next(db, queue.id, counter.id).number == 2
    qe.transition(db, t2.id, "complete")
    qe.transition(db, t1.id, "resume")
    qe.transition(db, t3.id, "cancel")
    assert qe.call_next(db, queue.id, counter.id).number == 1
    qe.transition(db, t1.id, "complete")
    assert qe.call_next(db, queue.id, counter.id).number == 4


def test_counter_serves_one_customer_at_a_time():
    db = SessionLocal()
    _, queue, (counter,) = _setup(db)
    qe.issue_token(db, queue.id)
    qe.issue_token(db, queue.id)
    qe.call_next(db, queue.id, counter.id)
    with pytest.raises(qe.QueueError):
        qe.call_next(db, queue.id, counter.id)


def test_no_show_frees_the_counter():
    db = SessionLocal()
    _, queue, (counter,) = _setup(db)
    qe.issue_token(db, queue.id)
    qe.issue_token(db, queue.id)
    absent = qe.call_next(db, queue.id, counter.id)
    assert qe.transition(db, absent.id, "no_show").status == TokenStatus.NO_SHOW
    assert qe.call_next(db, queue.id, counter.id).number == 2


def test_eta_uses_historical_service_duration():
    db = SessionLocal()
    _, queue, counters = _setup(db, counters=2)
    for _ in range(3):
        qe.issue_token(db, queue.id)
        called = qe.call_next(db, queue.id, counters[0].id)
        called.called_at = called.called_at - timedelta(seconds=120)
        db.commit()
        qe.transition(db, called.id, "complete")
    a, b, c = (qe.issue_token(db, queue.id) for _ in range(3))
    view = qe.token_view(db, c)
    assert view["position"] == 3
    assert view["estimated_wait_seconds"] == 120  # two ahead, 120s average, two counters


def test_cancel_is_rejected_once_called():
    db = SessionLocal()
    _, queue, (counter,) = _setup(db)
    token = qe.issue_token(db, queue.id)
    qe.call_next(db, queue.id, counter.id)
    with pytest.raises(qe.QueueError):
        qe.transition(db, token.id, "cancel")
