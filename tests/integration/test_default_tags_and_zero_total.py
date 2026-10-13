"""
Tests for default tag seeding and 0.00 total checkout edge cases.
"""
import os

import pytest

from app.database.connection import _get_party_db_path


def _drop(db_name):
    db_path = _get_party_db_path(db_name)
    for ext in ('', '-wal', '-shm', '-journal'):
        p = db_path + ext
        if os.path.exists(p):
            os.remove(p)


def test_default_tags_seeded_and_assigned(client):
    """Fresh DBs get default tags, assigned to the default products."""
    db_name = 'tags_test_party'
    try:
        # Login as admin (triggers DB auto-creation with seed products + tags)
        client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

        resp = client.get(f'/api/products/tags?db={db_name}')
        assert resp.status_code == 200
        tag_names = [t['name'] for t in resp.get_json()]
        assert 'Hot' in tag_names
        assert 'Popular' in tag_names

        # Products in the Hot Drinks subsection carry the 'Hot' tag
        sections = client.get(f'/api/products/?db={db_name}').get_json()
        hot_drinks = next(
            sub['id'] for section in sections
            for sub in section.get('subsections', [])
            if sub['name'] == 'Hot Drinks')
        products = client.get(
            f'/api/products/{hot_drinks}/products?db={db_name}').get_json()
        assert len(products) > 0
        tag_names = {t['name'] for p in products for t in p.get('tags', [])}
        assert 'Hot' in tag_names
    finally:
        _drop(db_name)


@pytest.mark.parametrize('payment_method,extra', [
    ('card', {}),
    ('cash', {'tendered': 0}),
])
def test_zero_total_checkout(clean_db, client, payment_method, extra):
    """100%-discounted sales close at 0.00 on any payment method."""
    db_name = clean_db

    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Setup product
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Free Coffee', 'price': 5.00, 'section_id': 1, 'subsection_id': 1
    })

    # Add to cart and apply 100% discount
    client.post(f'/api/cart/add?db={db_name}', json={'product_id': 1, 'quantity': 1})
    resp = client.post(f'/api/cart/discount?db={db_name}', json={'type': 'percentage', 'value': 100})
    assert resp.get_json()['total'] == 0.0

    body = {'payment_method': payment_method}
    body.update(extra)
    resp = client.post(f'/api/orders/checkout?db={db_name}', json=body)
    assert resp.status_code == 201
    assert resp.get_json()['total'] == 0.0

    # Verify order exists in recent orders
    resp = client.get(f'/api/orders/recent?db={db_name}')
    orders = resp.get_json()
    assert len(orders) == 1
    assert orders[0]['total'] == 0.0