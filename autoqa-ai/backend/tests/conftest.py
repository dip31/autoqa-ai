import pytest
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from database.init_db import init_db

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['JWT_SECRET_KEY'] = 'test-secret'
    
    # Use a separate test database if needed, but for unit tests we mock agents
    # For now, we utilize the real app instance
    with app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def setup_test_db():
    # Optional: logic to clear test tables before each test
    pass
