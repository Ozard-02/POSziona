"""
Party management API endpoints.
"""

from flask import Blueprint, request, jsonify
from app.services.party_service import (
    create_party_from_template,
    create_empty_party,
    list_parties,
    delete_party,
    duplicate_party,
    get_party_settings,
    update_party_setting,
)
from app.database import templates_db
from app.utils.logger import get_logger

logger = get_logger('api.parties')

parties_bp = Blueprint('parties', __name__)


# ============================================================
# TEMPLATE MANAGEMENT
# ============================================================

@parties_bp.route('/templates', methods=['GET'])
def get_templates():
    """Get all party templates."""
    return jsonify(templates_db.get_all_templates())


@parties_bp.route('/templates', methods=['POST'])
def create_template():
    """Create a new party template."""
    data = request.get_json()
    name = data.get('name', '').strip()
    description = data.get('description', '')

    if not name:
        return jsonify({'error': 'Template name is required'}), 400

    try:
        template_id = templates_db.create_template(name, description)
        return jsonify({'message': 'Template created', 'id': template_id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@parties_bp.route('/templates/<int:template_id>', methods=['GET'])
def get_template(template_id):
    """Get a single template."""
    template = templates_db.get_template(template_id)
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    return jsonify(template)


@parties_bp.route('/templates/<int:template_id>', methods=['DELETE'])
def remove_template(template_id):
    """Delete a template."""
    templates_db.delete_template(template_id)
    return jsonify({'message': 'Template deleted'})


@parties_bp.route('/templates/<int:template_id>/products', methods=['POST'])
def add_template_product(template_id):
    """Add a product to a template."""
    data = request.get_json()
    try:
        templates_db.add_template_product(
            template_id,
            name=data['name'],
            price=float(data['price']),
            section=data['section'],
            subsection=data['subsection'],
            sku=data.get('sku'),
            stock=int(data['stock']) if data.get('stock') else None
        )
        return jsonify({'message': 'Product added to template'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@parties_bp.route('/templates/<int:template_id>/products', methods=['GET'])
def get_template_products(template_id):
    """Get all products in a template."""
    return jsonify(templates_db.get_template_products(template_id))


@parties_bp.route('/templates/<int:template_id>/settings', methods=['GET'])
def get_template_settings(template_id):
    """Get all settings for a template."""
    return jsonify(templates_db.get_template_settings(template_id))


@parties_bp.route('/templates/<int:template_id>/settings', methods=['POST'])
def set_template_settings(template_id):
    """Set settings for a template."""
    data = request.get_json()
    for key, value in data.items():
        templates_db.set_template_setting(template_id, key, value)
    return jsonify({'message': 'Settings updated'})


# ============================================================
# PARTY MANAGEMENT
# ============================================================

@parties_bp.route('/', methods=['GET'])
def get_parties():
    """List all party databases."""
    return jsonify(list_parties())


@parties_bp.route('/', methods=['POST'])
def create_party():
    """Create a party from a template."""
    data = request.get_json()
    template_id = data.get('template_id')
    party_name = data.get('name', '').strip()

    if not template_id or not party_name:
        return jsonify({'error': 'template_id and name are required'}), 400

    try:
        db_name = create_party_from_template(
            party_name, template_id,
            data.get('start_date'), data.get('end_date')
        )
        return jsonify({
            'message': 'Party created',
            'db_name': db_name,
            'party_name': party_name
        }), 201
    except Exception as e:
        logger.error(f"Error creating party: {e}")
        return jsonify({'error': str(e)}), 400


@parties_bp.route('/create-empty', methods=['POST'])
def create_empty():
    """Create a new party without a template (manual creation)."""
    data = request.get_json()
    party_name = data.get('name', '').strip()
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    if not party_name:
        return jsonify({'error': 'Party name is required'}), 400

    try:
        db_name = create_empty_party(party_name, start_date, end_date)
        return jsonify({
            'message': 'Party created (empty)',
            'db_name': db_name,
            'party_name': party_name
        }), 201
    except Exception as e:
        logger.error(f"Error creating empty party: {e}")
        return jsonify({'error': str(e)}), 400


@parties_bp.route('/<db_name>', methods=['DELETE'])
def remove_party(db_name):
    """Delete a party database."""
    try:
        delete_party(db_name)
        return jsonify({'message': f'Party "{db_name}" deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@parties_bp.route('/<db_name>/duplicate', methods=['POST'])
def duplicate(db_name):
    """Duplicate a party."""
    data = request.get_json() or {}
    new_name = data.get('name', '').strip()
    if not new_name:
        return jsonify({'error': 'New party name is required'}), 400

    try:
        actual_db_name = duplicate_party(db_name, new_name)
        return jsonify({'message': 'Party duplicated', 'new_name': actual_db_name})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@parties_bp.route('/<db_name>/settings', methods=['GET'])
def get_party_settings_route(db_name):
    """Get settings for a party."""
    return jsonify(get_party_settings(db_name))


@parties_bp.route('/<db_name>/settings', methods=['POST'])
def set_party_settings_route(db_name):
    """Update settings for a party."""
    data = request.get_json()
    for key, value in data.items():
        update_party_setting(db_name, key, value)
    return jsonify({'message': 'Settings updated'})


# ============================================================
# TEMPLATE TAG MANAGEMENT
# ============================================================

@parties_bp.route('/templates/<int:template_id>/tags', methods=['GET'])
def get_template_tags_route(template_id):
    """Get all tags defined on a template."""
    return jsonify(templates_db.get_template_tags(template_id))


@parties_bp.route('/templates/<int:template_id>/tags', methods=['POST'])
def add_template_tag_route(template_id):
    """Add a tag definition to a template."""
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Tag name is required'}), 400
    tag_id = templates_db.add_template_tag(
        template_id,
        name=name,
        color=data.get('color', '#3498db'),
        bg_color=data.get('bg_color'),
        text_color=data.get('text_color')
    )
    return jsonify({'message': 'Template tag created', 'id': tag_id}), 201


@parties_bp.route('/templates/<int:template_id>/products/<int:product_id>/tags', methods=['POST'])
def assign_template_product_tag(template_id, product_id):
    """Assign an existing template tag to a template product by tag name."""
    data = request.get_json()
    tag_name = data.get('tag_name', '').strip()
    if not tag_name:
        return jsonify({'error': 'tag_name is required'}), 400
    templates_db.set_template_product_tags(template_id, product_id, [tag_name])
    return jsonify({'message': 'Tag assigned to template product'})
