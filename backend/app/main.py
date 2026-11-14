from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import engine as qe
from .database import Base, engine as db_engine, get_db
from .models import Business, Counter, Queue, Service, Token, TokenStatus
from .security import hash_key, new_api_key, new_code

STAFF_ACTIONS = set(qe.TRANSITIONS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=db_engine)  # use Alembic migrations for production
    yield


app = FastAPI(title="QueueLess API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(qe.QueueError)
async def _queue_error(_request, exc: qe.QueueError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


class BusinessIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    avg_service_seconds: int = Field(default=600, ge=30, le=7200)


class QueueIn(BaseModel):
    service_id: int
    name: str = Field(min_length=1, max_length=120)


class CounterIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class NextIn(BaseModel):
    counter_id: int


class JoinIn(BaseModel):
    customer_name: str | None = Field(default=None, max_length=80)


def _out(obj, *fields):
    return {f: getattr(obj, f) for f in fields}


def _token_out(t: Token) -> dict:
    return _out(t, "id", "number", "status", "counter_id", "customer_name", "public_code", "created_at")


def get_business(x_api_key: str = Header(default=""), db: Session = Depends(get_db)) -> Business:
    business = db.scalar(select(Business).where(Business.api_key_hash == hash_key(x_api_key))) if x_api_key else None
    if business is None:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
    return business


def _own_queue(db: Session, business: Business, queue_id: int) -> Queue:
    queue = db.scalar(select(Queue).where(Queue.id == queue_id, Queue.business_id == business.id))
    if queue is None:
        raise HTTPException(status_code=404, detail="Queue not found")
    return queue


def _queue_by_code(db: Session, code: str) -> Queue:
    queue = db.scalar(select(Queue).where(Queue.public_code == code))
    if queue is None:
        raise HTTPException(status_code=404, detail="Queue not found")
    return queue


def _token_by_code(db: Session, code: str) -> Token:
    token = db.scalar(select(Token).where(Token.public_code == code))
    if token is None:
        raise HTTPException(status_code=404, detail="Token not found")
    return token


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---- Business (authenticated) -------------------------------------------------

@app.post("/api/businesses", status_code=201)
def register_business(body: BusinessIn, db: Session = Depends(get_db)):
    key = new_api_key()
    business = Business(name=body.name, api_key_hash=hash_key(key))
    db.add(business)
    db.commit()
    return {"id": business.id, "name": business.name, "api_key": key}


@app.post("/api/services", status_code=201)
def create_service(body: ServiceIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    service = Service(business_id=business.id, name=body.name, avg_service_seconds=body.avg_service_seconds)
    db.add(service)
    db.commit()
    return _out(service, "id", "name", "avg_service_seconds")


@app.post("/api/queues", status_code=201)
def create_queue(body: QueueIn, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    service = db.scalar(select(Service).where(Service.id == body.service_id, Service.business_id == business.id))
    if service is None:
        raise HTTPException(status_code=404, detail="Service not found")
    queue = Queue(business_id=business.id, service_id=service.id, name=body.name, public_code=new_code())
    db.add(queue)
    db.commit()
    return _out(queue, "id", "name", "public_code", "is_open")


@app.post("/api/queues/{queue_id}/counters", status_code=201)
def add_counter(queue_id: int, body: CounterIn, business: Business = Depends(get_business),
                db: Session = Depends(get_db)):
    _own_queue(db, business, queue_id)
    counter = Counter(queue_id=queue_id, name=body.name)
    db.add(counter)
    db.commit()
    return _out(counter, "id", "name", "is_open")


@app.get("/api/queues/{queue_id}/board")
def board(queue_id: int, business: Business = Depends(get_business), db: Session = Depends(get_db)):
    queue = _own_queue(db, business, queue_id)
    tokens = db.scalars(select(Token).where(
        Token.queue_id == queue.id,
        Token.status.in_([TokenStatus.WAITING, TokenStatus.HELD, TokenStatus.CALLED]),
    ).order_by(Token.number)).all()
    counters = db.scalars(select(Counter).where(Counter.queue_id == queue.id).order_by(Counter.id)).all()
    return {
        "queue": _out(queue, "id", "name", "public_code", "is_open"),
        "counters": [_out(c, "id", "name", "is_open") for c in counters],
        "tokens": [_token_out(t) for t in tokens],
    }


@app.post("/api/queues/{queue_id}/next")
def call_next(queue_id: int, body: NextIn, business: Business = Depends(get_business),
              db: Session = Depends(get_db)):
    _own_queue(db, business, queue_id)
    return _token_out(qe.call_next(db, queue_id, body.counter_id))


@app.post("/api/tokens/{token_id}/{action}")
def staff_action(token_id: int, action: str, business: Business = Depends(get_business),
                 db: Session = Depends(get_db)):
    if action not in STAFF_ACTIONS:
        raise HTTPException(status_code=404, detail="Unknown action")
    return _token_out(qe.transition(db, token_id, action, business_id=business.id))


# ---- Customer (public, token/queue codes act as unguessable capabilities) ----

@app.get("/api/public/queues/{code}")
def public_queue(code: str, db: Session = Depends(get_db)):
    return qe.queue_status(db, _queue_by_code(db, code))


@app.post("/api/public/queues/{code}/join", status_code=201)
def public_join(code: str, body: JoinIn | None = None, db: Session = Depends(get_db)):
    queue = _queue_by_code(db, code)
    token = qe.issue_token(db, queue.id, body.customer_name if body else None)
    return qe.token_view(db, token)


@app.get("/api/public/tokens/{code}")
def public_token(code: str, db: Session = Depends(get_db)):
    return qe.token_view(db, _token_by_code(db, code))


@app.post("/api/public/tokens/{code}/cancel")
def public_cancel(code: str, db: Session = Depends(get_db)):
    token = _token_by_code(db, code)
    qe.transition(db, token.id, "cancel")
    return qe.token_view(db, token)


from .customer_page import router as customer_router  # noqa: E402

app.include_router(customer_router)
