from fastapi.testclient import TestClient
import pytest

from src.mes.api import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_simulation_between_tests():
    client.post('/api/v2/simulation/reset')
    yield
