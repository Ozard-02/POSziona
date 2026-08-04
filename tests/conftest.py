"""
Pytest configuration and fixtures for Posziona tests.
"""
import os
import sys
import shutil
import sqlite3
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.database.connection import PartyDatabase, TEMPLATES_DB, PARTY_DB_DIR, _init_default_operators
from app.database.schema import get_party_schema, get_templates_schema


TEST_PARTY_NAME = 'test_party'


@pytest.fixture
def app():
    """Create a test Flask application."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def db_path():
    """Path to the test database."""
    return f"{TEST_PARTY_NAME}.db"


@pytest.fixture
def clean_db():
    """Ensure a clean test database before and after tests."""
    # Clean up before
    _cleanup_test_db()
    _cleanup_test_templates()
    
    # Create test DB with schema
    schema = get_party_schema()
    db_full_path = os.path.join(PARTY_DB_DIR, f"{TEST_PARTY_NAME}.db")
    os.makedirs(PARTY_DB_DIR, exist_ok=True)
    
    conn = sqlite3.connect(db_full_path)
    conn.executescript(schema)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.commit()
    conn.close()
    
    # Initialize default operators
    _init_default_operators(db_full_path)
    
    yield TEST_PARTY_NAME
    
    # Clean up after
    _cleanup_test_db()
    _cleanup_test_templates()


def _cleanup_test_db():
    """Remove test database files."""
    db_path = os.path.join(PARTY_DB_DIR, f"{TEST_PARTY_NAME}.db")
    for ext in ['', '-wal', '-shm']:
        path = db_path + ext
        if os.path.exists(path):
            os.remove(path)


def _cleanup_test_templates():
    """Remove all templates from the shared templates database.
    
    This ensures tests that create templates with fixed names
    don't fail due to UNIQUE constraint violations from previous runs.
    """
    if os.path.exists(TEMPLATES_DB):
        conn = sqlite3.connect(TEMPLATES_DB)
        try:
            # Ensure all template tables exist (in case DB was created before schema update)
            conn.executescript(get_templates_schema())
            conn.execute('DELETE FROM templates')
            conn.execute('DELETE FROM template_sections')
            conn.execute('DELETE FROM template_subsections')
            conn.execute('DELETE FROM template_products')
            conn.execute('DELETE FROM template_settings')
            conn.execute('DELETE FROM template_tags')
            conn.execute('DELETE FROM template_product_tags')
            conn.commit()
        finally:
            conn.close()
