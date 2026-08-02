"""
Products API endpoints.
"""

from flask import Blueprint, request, jsonify
from app.services.product_service import (
    get_all_sections_with_subsections,
    get_products_by_subsection,
    get_product_by_id,
    create_product,
    update_product,
    delete_product,
    import_products_from_csv,
    create_section,
    create_subsection,
    get_sections,
    get_subsections,
    get_all_products,
    get_all_tags,
    get_tag_by_id,
    create_tag,
    update_tag,
    delete_tag,
    assign_tag_to_product,
    remove_tag_from_product,
    set_product_tags,
    get_product_tags,
    search_products,
    update_product_status,
    bulk_update_products,
    reorder_sections,
)
from app.utils.logger import get_logger

logger = get_logger('api.products')

products_bp = Blueprint('products', __name__)


# ============================================================
# SECTION ENDPOINTS
# ============================================================

@products_bp.route('/', methods=['GET'])
def list_sections():
    """Get all sections with their subsections (2-level tree)."""
    db = request.args.get('db', 'default')
    sections = get_all_sections_with_subsections(db)
    return jsonify(sections)


@products_bp.route('/sections', methods=['GET'])
def get_all_sections():
    """Get all sections (flat list)."""
    db = request.args.get('db', 'default')
    return jsonify(get_sections(db))


@products_bp.route('/sections', methods=['POST'])
def add_section():
    """Create a new section."""
    db = request.args.get('db', 'default')
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Section name is required'}), 400

    create_section(db, name)
    return jsonify({'message': f'Section "{name}" created'}), 201


@products_bp.route('/sections/reorder', methods=['POST'])
def reorder_sections_route():
    """Reorder sections by setting sort_order based on provided order."""
    db = request.args.get('db', 'default')
    data = request.get_json()
    section_ids = data.get('section_ids', [])
    if not section_ids or not isinstance(section_ids, list):
        return jsonify({'error': 'section_ids list is required'}), 400
    reorder_sections(db, section_ids)
    return jsonify({'message': 'Sections reordered'})


@products_bp.route('/subsections', methods=['POST'])
def add_subsection():
    """Create a new subsection under a section."""
    db = request.args.get('db', 'default')
    data = request.get_json()
    section_id = data.get('section_id')
    name = data.get('name', '').strip()
    if not name or section_id is None:
        return jsonify({'error': 'name and section_id are required'}), 400

    create_subsection(db, section_id, name)
    return jsonify({'message': f'Subsection "{name}" created'}), 201


# ============================================================
# PRODUCT ENDPOINTS
# ============================================================

@products_bp.route('/all', methods=['GET'])
def list_all_products():
    """Get all products across all sections (for admin export/list)."""
    db = request.args.get('db', 'default')
    return jsonify(get_all_products(db))


@products_bp.route('/search', methods=['GET'])
def search_products_route():
    """Search and filter products (admin only).

    Query params:
        search: Free-text search on name/SKU.
        section_id: Filter by section ID.
        subsection_id: Filter by subsection ID.
        tag_ids: Comma-separated tag IDs — products must have ALL of these.
        is_active: 'true', 'false', or omit for all.
    """
    db = request.args.get('db', 'default')
    search = request.args.get('search', None)
    section_id = request.args.get('section_id', None)
    subsection_id = request.args.get('subsection_id', None)

    tag_ids_raw = request.args.get('tag_ids', None)
    tag_ids = None
    if tag_ids_raw:
        tag_ids = [int(t) for t in tag_ids_raw.split(',') if t.strip()]

    is_active_raw = request.args.get('is_active', None)
    is_active = None
    if is_active_raw == 'true':
        is_active = True
    elif is_active_raw == 'false':
        is_active = False

    if section_id:
        section_id = int(section_id)
    if subsection_id:
        subsection_id = int(subsection_id)

    results = search_products(
        db,
        search=search,
        section_id=section_id,
        subsection_id=subsection_id,
        tag_ids=tag_ids,
        is_active=is_active
    )
    return jsonify(results)


@products_bp.route('/products/bulk', methods=['POST'])
def bulk_update_products_route():
    """Bulk update multiple products (admin only).

    Body:
        product_ids: List of product IDs.
        updates: Dict of field -> new value. Supported: name, price, sku,
                 section_id, subsection_id, stock, is_active, is_archived,
                 tags (list of tag IDs).
    """
    db = request.args.get('db', 'default')
    if not _is_admin():
        return jsonify({'error': 'Admin access required'}), 403

    data = request.get_json()
    product_ids = data.get('product_ids', [])
    updates = data.get('updates', {})

    if not product_ids:
        return jsonify({'error': 'product_ids is required'}), 400
    if not updates:
        return jsonify({'error': 'updates is required'}), 400

    # Validate price if present in bulk updates
    if 'price' in updates:
        try:
            price = float(updates['price'])
            if price < 0:
                return jsonify({'error': 'Price must be non-negative'}), 400
        except (TypeError, ValueError):
            return jsonify({'error': 'Price must be a valid number'}), 400

    count = bulk_update_products(db, product_ids, updates)
    return jsonify({'message': f'Updated {count} products', 'count': count})


@products_bp.route('/products/<int:product_id>/status', methods=['PUT'])
def update_product_status_route(product_id):
    """Toggle active/archived status for a single product (admin only)."""
    db = request.args.get('db', 'default')
    if not _is_admin():
        return jsonify({'error': 'Admin access required'}), 403

    data = request.get_json()
    is_active = data.get('is_active')
    is_archived = data.get('is_archived')

    if is_active is None and is_archived is None:
        return jsonify({'error': 'is_active or is_archived is required'}), 400

    update_product_status(
        db, product_id,
        is_active=is_active,
        is_archived=is_archived
    )
    return jsonify({'message': 'Product status updated'})


@products_bp.route('/<int:subsection_id>/products', methods=['GET'])
def list_products(subsection_id):
    """Get all products in a subsection."""
    db = request.args.get('db', 'default')
    products = get_products_by_subsection(db, subsection_id)
    return jsonify(products)


@products_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """Get a single product by ID."""
    db = request.args.get('db', 'default')
    product = get_product_by_id(db, product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    return jsonify(product)


@products_bp.route('/products', methods=['POST'])
def add_product():
    """Create a new product."""
    db = request.args.get('db', 'default')
    data = request.get_json()

    required = ['name', 'price', 'section_id', 'subsection_id']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400

    name = data.get('name', '').strip() if isinstance(data.get('name'), str) else data.get('name')
    if not name:
        return jsonify({'error': 'name must not be empty'}), 400

    try:
        price = float(data['price'])
        if price < 0:
            return jsonify({'error': 'Price must be non-negative'}), 400
    except (TypeError, ValueError):
        return jsonify({'error': 'Price must be a valid number'}), 400

    try:
        product_id = create_product(
            db,
            name=name,
            price=price,
            section_id=int(data['section_id']),
            subsection_id=int(data['subsection_id']),
            sku=data.get('sku'),
            stock=int(data['stock']) if data.get('stock') is not None else None
        )
        # Assign tags if provided
        tag_ids = data.get('tags') or []
        if tag_ids:
            set_product_tags(db, product_id, [int(t) for t in tag_ids])
        return jsonify({'message': 'Product created', 'id': product_id}), 201
    except Exception as e:
        logger.error(f"Error creating product: {e}")
        return jsonify({'error': str(e)}), 400


@products_bp.route('/products/<int:product_id>', methods=['PUT'])
def edit_product(product_id):
    """Update a product."""
    db = request.args.get('db', 'default')
    data = request.get_json()

    try:
        # Validate price if present
        if 'price' in data:
            price = float(data['price'])
            if price < 0:
                return jsonify({'error': 'Price must be non-negative'}), 400

        update_product(db, product_id, **{
            k: v for k, v in data.items()
            if k in ('name', 'price', 'sku', 'section_id', 'subsection_id', 'stock', 'is_active')
        })
        # Update tags if provided
        if 'tags' in data:
            tag_ids = data['tags'] or []
            set_product_tags(db, product_id, [int(t) for t in tag_ids])
        return jsonify({'message': 'Product updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@products_bp.route('/products/<int:product_id>', methods=['DELETE'])
def remove_product(product_id):
    """Delete or archive a product."""
    db = request.args.get('db', 'default')
    deleted = delete_product(db, product_id)
    if deleted is None:
        return jsonify({'error': 'Product not found'}), 404
    elif deleted:
        return jsonify({'message': 'Product deleted'})
    else:
        return jsonify({'message': 'Product archived (has sales history)'})


# ============================================================
# TAG MANAGEMENT ENDPOINTS
# ============================================================

@products_bp.route('/tags', methods=['GET'])
def list_tags():
    """Get all tags for the active party."""
    db = request.args.get('db', 'default')
    return jsonify(get_all_tags(db))


@products_bp.route('/tags', methods=['POST'])
def add_tag():
    """Create a new tag (admin only)."""
    db = request.args.get('db', 'default')
    if request.args.get('require_admin', '1') == '1' and not _is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Tag name is required'}), 400
    tag_id = create_tag(
        db,
        name=name,
        color=data.get('color', '#3498db'),
        bg_color=data.get('bg_color'),
        text_color=data.get('text_color')
    )
    return jsonify({'message': 'Tag created', 'id': tag_id}), 201


@products_bp.route('/tags/<int:tag_id>', methods=['GET'])
def get_tag(tag_id):
    """Get a single tag by ID."""
    db = request.args.get('db', 'default')
    tag = get_tag_by_id(db, tag_id)
    if not tag:
        return jsonify({'error': 'Tag not found'}), 404
    return jsonify(tag)


@products_bp.route('/tags/<int:tag_id>', methods=['PUT'])
def edit_tag(tag_id):
    """Update a tag including its styling rules (admin only)."""
    db = request.args.get('db', 'default')
    if not _is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    data = request.get_json()
    try:
        update_tag(
            db, tag_id,
            name=data.get('name'),
            color=data.get('color'),
            bg_color=data.get('bg_color'),
            text_color=data.get('text_color'),
            is_active=data.get('is_active')
        )
        return jsonify({'message': 'Tag updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@products_bp.route('/tags/<int:tag_id>', methods=['DELETE'])
def remove_tag(tag_id):
    """Delete a tag (admin only)."""
    db = request.args.get('db', 'default')
    if not _is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    delete_tag(db, tag_id)
    return jsonify({'message': 'Tag deleted'})


@products_bp.route('/<int:product_id>/tags', methods=['GET'])
def get_product_tag_list(product_id):
    """Get all tags assigned to a product."""
    db = request.args.get('db', 'default')
    return jsonify(get_product_tags(db, product_id))


@products_bp.route('/<int:product_id>/tags', methods=['POST'])
def assign_product_tag(product_id):
    """Assign a tag to a product (admin only)."""
    db = request.args.get('db', 'default')
    if request.args.get('require_admin', '1') == '1' and not _is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    data = request.get_json()
    tag_id = data.get('tag_id')
    if tag_id is None:
        return jsonify({'error': 'tag_id is required'}), 400
    assign_tag_to_product(db, product_id, int(tag_id))
    return jsonify({'message': 'Tag assigned to product'})


@products_bp.route('/<int:product_id>/tags/<int:tag_id>', methods=['DELETE'])
def unassign_product_tag(product_id, tag_id):
    """Remove a tag from a product (admin only)."""
    db = request.args.get('db', 'default')
    if request.args.get('require_admin', '1') == '1' and not _is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    remove_tag_from_product(db, product_id, tag_id)
    return jsonify({'message': 'Tag removed from product'})


@products_bp.route('/<int:product_id>/tags', methods=['PUT'])
def set_product_tag_list(product_id):
    """Replace all tags on a product (admin only)."""
    db = request.args.get('db', 'default')
    if request.args.get('require_admin', '1') == '1' and not _is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    data = request.get_json()
    tag_ids = data.get('tags', [])
    set_product_tags(db, product_id, [int(t) for t in tag_ids])
    return jsonify({'message': 'Product tags updated'})


def _is_admin():
    """Check if the current session user is an admin."""
    from flask import session
    return session.get('operator_role') == 'admin'


# ============================================================
# CSV IMPORT / EXPORT
# ============================================================

@products_bp.route('/import-csv', methods=['POST'])
def import_csv_file():
    """Import products from a CSV file upload or JSON rows."""
    db = request.args.get('db', 'default')
    data = request.get_json()

    csv_rows = data.get('rows', [])
    if not csv_rows:
        return jsonify({'error': 'No CSV rows provided'}), 400

    try:
        import_products_from_csv(db, csv_rows)
        return jsonify({'message': f'Imported {len(csv_rows)} products'}), 201
    except Exception as e:
        logger.error(f"CSV import error: {e}")
        return jsonify({'error': str(e)}), 400


@products_bp.route('/export', methods=['GET'])
def export_products():
    """Export all products as CSV."""
    import csv
    import io
    db = request.args.get('db', 'default')

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['section', 'subsection', 'name', 'price', 'sku', 'stock_count'])

    products = get_all_products(db)
    for p in products:
        writer.writerow([
            p.get('section_name', ''),
            p.get('subsection_name', ''),
            p['name'],
            p['price'],
            p.get('sku', '') or '',
            p.get('stock_count', '') if p.get('stock_count') is not None else ''
        ])

    # Return as JSON with CSV string
    return jsonify({
        'csv': output.getvalue(),
        'filename': 'products_export.csv'
    })
