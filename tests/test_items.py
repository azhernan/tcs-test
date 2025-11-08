import pytest
from httpx import Client

from api.app.main import app


@pytest.fixture(scope="module")
def client():
    # Para tests rápidos en local (sin docker) usar httpx Client
    with Client(app=app, base_url="http://testserver") as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_and_list(client):
    r = client.post("/items", json={"name": "notebook", "price": 123.45})
    assert r.status_code == 201
    item = r.json()
    assert item["id"] >= 1
    r2 = client.get("/items")
    assert r2.status_code == 200
    assert any(i["name"] == "notebook" for i in r2.json())
