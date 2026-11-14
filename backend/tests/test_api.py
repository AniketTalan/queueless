from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register(name="Clinic"):
    r = client.post("/api/businesses", json={"name": name})
    assert r.status_code == 201
    return {"X-API-Key": r.json()["api_key"]}


def _setup_queue(headers):
    svc = client.post("/api/services", json={"name": "General OPD", "avg_service_seconds": 300}, headers=headers).json()
    queue = client.post("/api/queues", json={"service_id": svc["id"], "name": "Dr. Rao"}, headers=headers).json()
    counter = client.post(f"/api/queues/{queue['id']}/counters", json={"name": "Room 1"}, headers=headers).json()
    return queue, counter


def test_registration_validates_input():
    assert client.post("/api/businesses", json={"name": "x"}).status_code == 422


def test_staff_routes_require_a_valid_api_key():
    assert client.post("/api/services", json={"name": "A"}).status_code == 401
    assert client.post("/api/services", json={"name": "A"}, headers={"X-API-Key": "bogus"}).status_code == 401


def test_customer_and_staff_journey():
    headers = _register()
    queue, counter = _setup_queue(headers)
    code = queue["public_code"]
    first = client.post(f"/api/public/queues/{code}/join", json={"customer_name": "Asha"}).json()
    second = client.post(f"/api/public/queues/{code}/join", json={}).json()
    assert first["number"] == 1 and first["position"] == 1
    assert second["position"] == 2 and second["estimated_wait_seconds"] == 300

    called = client.post(f"/api/queues/{queue['id']}/next", json={"counter_id": counter["id"]}, headers=headers).json()
    assert called["number"] == 1 and called["status"] == "called"
    status = client.get(f"/api/public/tokens/{first['token_code']}").json()
    assert status["status"] == "called" and status["now_serving"] == [1]

    client.post(f"/api/tokens/{called['id']}/complete", headers=headers)
    cancelled = client.post(f"/api/public/tokens/{second['token_code']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert client.post(f"/api/queues/{queue['id']}/next", json={"counter_id": counter["id"]},
                       headers=headers).status_code == 404


def test_businesses_cannot_access_each_others_queues_or_tokens():
    owner = _register("Owner Clinic")
    intruder = _register("Other Clinic")
    queue, counter = _setup_queue(owner)
    client.post(f"/api/public/queues/{queue['public_code']}/join", json={})
    called = client.post(f"/api/queues/{queue['id']}/next", json={"counter_id": counter["id"]}, headers=owner).json()

    assert client.get(f"/api/queues/{queue['id']}/board", headers=intruder).status_code == 404
    assert client.post(f"/api/queues/{queue['id']}/next", json={"counter_id": counter["id"]},
                       headers=intruder).status_code == 404
    assert client.post(f"/api/tokens/{called['id']}/complete", headers=intruder).status_code == 404
    assert client.post(f"/api/tokens/{called['id']}/complete", headers=owner).status_code == 200


def test_error_responses_are_meaningful():
    assert client.get("/api/public/tokens/does-not-exist").json()["detail"] == "Token not found"
    headers = _register()
    queue, _ = _setup_queue(headers)
    assert client.post(f"/api/tokens/1/fly", headers=headers).status_code == 404
