from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_customer_page_is_served_as_html():
    response = client.get("/q/any-code")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Get my token" in response.text
    assert "/api/public/queues/" in response.text
