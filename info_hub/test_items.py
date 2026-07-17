from fastapi.testclient import TestClient
from app.main import app

from app.database import get_db

def override_get_db():
    class DummyDB:
        def get_item(self):
            return [
                {"id": 1, "name": "Ноутбук", "description": "This is item 1."},
                {"id": 2, "name": "Телефон", "description": "This is item 2."},
            ]
    return DummyDB()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def test_create_items():
    response = client.post("/items/", json={"id": 1, "name": "Ноутбук", "description": "This is item 1."})
    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "Ноутбук", "description": "This is item 1."}


def test_get_items():
    response = client.get("/items/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

