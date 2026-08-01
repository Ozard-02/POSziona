"""
Unit tests for database connection and schema.
"""
import os
import sqlite3
import pytest

from app.database.connection import PartyDatabase, TEMPLATES_DB, PARTY_DB_DIR
from app.database.schema import get_party_schema, get_templates_schema
from app.models.product import Product
from app.models.cart import Cart
from app.models.operator import Operator
from app.models.tag import Tag


def test_party_schema_has_all_tables():
    """Verify the party schema creates all expected tables."""
    schema = get_party_schema()
    
    expected_tables = [
        'products', 'sections', 'subsections', 'operators',
        'orders', 'order_items', 'payments', 'audit_log', 'settings',
        'tags', 'product_tags'
    ]
    
    for table in expected_tables:
        assert f'CREATE TABLE IF NOT EXISTS {table}' in schema


def test_templates_schema_has_all_tables():
    """Verify the templates schema creates all expected tables."""
    schema = get_templates_schema()
    
    expected_tables = [
        'templates', 'template_sections', 'template_subsections',
        'template_products', 'template_settings',
        'template_tags', 'template_product_tags'
    ]
    
    for table in expected_tables:
        assert f'CREATE TABLE IF NOT EXISTS {table}' in schema


def test_product_model():
    """Test the Product model."""
    p = Product(
        id=1,
        name='Small Coffee',
        price=2.50,
        sku='COF-S',
        section_id=1,
        subsection_id=2,
        stock_count=None
    )
    
    assert p.is_unlimited == True
    assert p.is_in_stock == True
    assert p.display_name == 'Small Coffee'


def test_product_stock_limited():
    """Test product with limited stock."""
    p = Product(id=1, name='Test', price=1.0, stock_count=5)
    assert p.is_unlimited == False
    assert p.is_in_stock == True
    
    p.stock_count = 0
    assert p.is_in_stock == False


def test_cart_model():
    """Test cart operations."""
    cart = Cart()
    assert cart.is_empty() == True
    assert cart.total == 0.0
    
    p = Product(id=1, name='Coffee', price=2.50)
    cart.add_item(p)
    assert len(cart.items) == 1
    assert cart.items[0].quantity == 1
    
    cart.add_item(p)
    assert cart.items[0].quantity == 2
    assert cart.subtotal == 5.0
    
    # Test discount
    cart.apply_discount('percentage', 10)
    assert cart.discount_amount == 0.5
    assert cart.total == 4.5
    
    # Test fixed discount
    cart.clear_discount()
    cart.apply_discount('fixed', 1.0)
    assert cart.discount_amount == 1.0
    assert cart.total == 4.0
    
    # Test clear
    cart.clear()
    assert cart.is_empty() == True


def test_operator_model():
    """Test operator model."""
    op = Operator(id=1, name='admin', role='admin')
    assert op.is_admin == True
    assert op.display_role == 'Admin'
    
    op2 = Operator(id=2, name='bob', role='operator')
    assert op2.is_admin == False
    assert op2.display_role == 'Operator'


def test_tag_model():
    """Test the Tag model."""
    # Default tag
    t = Tag(id=1, name='Hot', color='#e74c3c', bg_color='#ffecec', text_color='#c0392b')
    assert t.display_name == 'Hot'
    assert t.has_bg_color == True
    assert t.has_text_color == True
    assert t.effective_color == '#e74c3c'

    # Tag with no styling overrides
    t2 = Tag(id=2, name='New', color='#3498db')
    assert t2.has_bg_color == False
    assert t2.has_text_color == False
    assert t2.effective_color == '#3498db'

    # Inactive tag
    t3 = Tag(id=3, name='Old', is_active=False)
    assert t3.is_active == False
