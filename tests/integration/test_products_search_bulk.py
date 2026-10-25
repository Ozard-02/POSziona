"""Product search/filter and bulk edit. One behavior per test."""
import pytest


@pytest.fixture
def admin_client(clean_db, client):
    """A client logged in as admin."""
    client.post(f'/api/auth/login/admin?db={clean_db}', json={'pin': '0000'})
    return client


def _seed_catalog(c, db):
    c.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    c.post(f'/api/products/sections?db={db}', json={'name': 'Food'})
    c.post(f'/api/products/subsections?db={db}',
           json={'section_id': 1, 'name': 'Coffee'})
    c.post(f'/api/products/subsections?db={db}',
           json={'section_id': 2, 'name': 'Snacks'})
    c.post(f'/api/products/products?db={db}', json={
        'name': 'Large Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1})
    c.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 1.50, 'section_id': 1, 'subsection_id': 1,
        'sku': 'SKU-001'})
    c.post(f'/api/products/products?db={db}', json={
        'name': 'Chips', 'price': 2.00, 'section_id': 2, 'subsection_id': 2})


@pytest.mark.parametrize('query,names', [
    ('search=Coffee', ['Large Coffee', 'Small Coffee']),
    ('search=SKU-001', ['Small Coffee']),
    ('search=nonexistent', []),
])
def test_search(admin_client, clean_db, query, names):
    """Free-text search matches names and SKUs; misses come back empty."""
    db = clean_db
    _seed_catalog(admin_client, db)

    resp = admin_client.get(f'/api/products/search?db={db}&{query}')
    assert resp.status_code == 200
    assert sorted(p['name'] for p in resp.get_json()) == sorted(names)


@pytest.mark.parametrize('query,names', [
    ('section_id=1', ['Large Coffee', 'Small Coffee']),
    ('subsection_id=2', ['Chips']),
])
def test_filter_by_section_or_subsection(admin_client, clean_db, query, names):
    """Section/subsection filters scope the catalog."""
    db = clean_db
    _seed_catalog(admin_client, db)

    resp = admin_client.get(f'/api/products/search?db={db}&{query}')
    assert sorted(p['name'] for p in resp.get_json()) == sorted(names)


def test_filter_by_tag(admin_client, clean_db):
    """Tag filter requires ALL specified tags."""
    db = clean_db
    c = admin_client
    c.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    c.post(f'/api/products/subsections?db={db}',
           json={'section_id': 1, 'name': 'Coffee'})
    c.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee', 'price': 1.50, 'section_id': 1, 'subsection_id': 1})
    c.post(f'/api/products/products?db={db}', json={
        'name': 'Tea', 'price': 1.00, 'section_id': 1, 'subsection_id': 1})

    tag1 = c.post(f'/api/products/tags?db={db}',
                  json={'name': 'Hot'}).get_json()['id']
    tag2 = c.post(f'/api/products/tags?db={db}',
                  json={'name': 'Popular'}).get_json()['id']
    c.post(f'/api/products/1/tags?db={db}', json={'tag_id': tag1})
    c.post(f'/api/products/1/tags?db={db}', json={'tag_id': tag2})
    c.post(f'/api/products/2/tags?db={db}', json={'tag_id': tag1})

    names = lambda q: sorted(
        p['name'] for p in c.get(f'/api/products/search?db={db}&{q}').get_json())
    assert names(f'tag_ids={tag1}') == ['Coffee', 'Tea']
    assert names(f'tag_ids={tag1},{tag2}') == ['Coffee']


def test_filter_by_active_status(admin_client, clean_db):
    """Active/inactive filter (canonical copy; stock-module dupe removed)."""
    db = clean_db
    c = admin_client
    c.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    c.post(f'/api/products/subsections?db={db}',
           json={'section_id': 1, 'name': 'Coffee'})
    c.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee', 'price': 1.50, 'section_id': 1, 'subsection_id': 1})

    assert c.put(f'/api/products/products/1/status?db={db}',
                 json={'is_active': False}).status_code == 200
    assert c.get(f'/api/products/search?db={db}&is_active=true').get_json() == []
    assert len(c.get(f'/api/products/search?db={db}&is_active=false').get_json()) == 1


@pytest.mark.parametrize('updates,check', [
    ({'price': 5.00}, 'price'),
    ({'is_active': False}, 'inactive'),
])
def test_bulk_update(admin_client, clean_db, updates, check):
    """Bulk edits apply to every listed product."""
    db = clean_db
    c = admin_client
    c.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    c.post(f'/api/products/subsections?db={db}',
           json={'section_id': 1, 'name': 'Coffee'})
    for name, price in (('Coffee1', 1.00), ('Coffee2', 2.00)):
        c.post(f'/api/products/products?db={db}', json={
            'name': name, 'price': price, 'section_id': 1, 'subsection_id': 1})

    resp = c.post(f'/api/products/products/bulk?db={db}', json={
        'product_ids': [1, 2], 'updates': updates})
    assert resp.status_code == 200
    assert resp.get_json()['count'] == 2

    products = c.get(f'/api/products/search?db={db}').get_json()
    if check == 'price':
        assert all(p['price'] == 5.00 for p in products)
    else:
        assert len(c.get(
            f'/api/products/search?db={db}&is_active=false').get_json()) == 2


def test_bulk_assign_tags(admin_client, clean_db):
    """Bulk tag assignment lands on every listed product."""
    db = clean_db
    c = admin_client
    c.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    c.post(f'/api/products/subsections?db={db}',
           json={'section_id': 1, 'name': 'Coffee'})
    for name in ('Coffee1', 'Coffee2'):
        c.post(f'/api/products/products?db={db}', json={
            'name': name, 'price': 1.00, 'section_id': 1, 'subsection_id': 1})
    tag_id = c.post(f'/api/products/tags?db={db}',
                    json={'name': 'Hot'}).get_json()['id']

    resp = c.post(f'/api/products/products/bulk?db={db}', json={
        'product_ids': [1, 2], 'updates': {'tags': [tag_id]}})
    assert resp.status_code == 200

    for p in c.get(f'/api/products/search?db={db}').get_json():
        assert 'Hot' in [t['name'] for t in p['tags']]


def test_bulk_update_requires_admin(client, clean_db):
    """Operators get 403 on bulk edit (real operator login, no session hack)."""
    db = clean_db
    assert client.post(f'/api/auth/login?db={db}',
                       json={'pin': '1234'}).status_code == 200

    resp = client.post(f'/api/products/products/bulk?db={db}', json={
        'product_ids': [1], 'updates': {'price': 5.00}})
    assert resp.status_code == 403


def test_concurrent_sections_get_unique_sort_order(clean_db):
    """Parallel creates never share a sort_order (R20).

    Old code did SELECT MAX(sort_order) then INSERT: two racing creators
    read the same max and both appended at the same position.
    """
    import threading

    from app.database.connection import PartyDatabase
    from app.services.product_service import create_section

    db = clean_db
    barrier = threading.Barrier(2)
    errors = []

    def _create(prefix):
        try:
            barrier.wait(timeout=5)
            for i in range(40):
                create_section(db, f'{prefix}-{i}')
        except Exception as e:  # noqa: BLE001 — collected, asserted below
            errors.append(e)

    threads = [threading.Thread(target=_create, args=(f'T{n}',))
               for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert errors == []
    with PartyDatabase(db) as conn:
        orders = [row['sort_order'] for row in
                  conn.execute('SELECT sort_order FROM sections').fetchall()]
    assert sorted(orders) == list(range(1, 81)), 'no duplicates, no gaps'
