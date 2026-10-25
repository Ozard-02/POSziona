"""
Admin settings UI: scope grouping (I1 audit 2026-10-25).

The settings screen must mirror the real two-tier model:
- counter settings apply to EVERY party (device-global),
- receipt/snapshot settings belong to the selected party.

Pin the structure so a future reshuffle cannot quietly move a
device-global knob (e.g. printer_cut) back under the per-party block.
"""


def _html(client):
    r = client.get('/admin')
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_settings_groups_follow_the_real_scope(client):
    """Counter groups before the party block; printer_cut lives with Printer."""
    html = _html(client)

    counter_scope = html.index('data-i18n="settings_counter_scope"')
    party_scope = html.index('data-i18n="settings_party_scope"')
    assert counter_scope < party_scope

    # Device-global groups sit in the counter half
    for marker in ('data-i18n="group_pos"', 'data-i18n="group_printer"',
                   'name="server_name"', 'name="default_payment_method"',
                   'name="printer_cut"'):
        assert counter_scope < html.index(marker) < party_scope, marker

    # Per-party groups sit in the party half
    for marker in ('data-i18n="group_receipt"', 'data-i18n="group_snapshots"',
                   'name="receipt_header"', 'name="snapshot_interval_minutes"',
                   'name="snapshot_keep_count"'):
        assert html.index(marker) > party_scope, marker


def test_settings_ui_has_no_dead_knobs(client):
    """Only settings something actually consumes are exposed (I1).

    tax_rate and auto_logout_minutes exist in DEFAULT_SETTINGS but no
    code reads them: shipping them as knobs would silently do nothing.
    """
    html = _html(client)
    assert 'name="tax_rate"' not in html
    assert 'name="auto_logout_minutes"' not in html
    # Snapshot retention IS consumed (backup scheduler): must be editable
    assert 'name="snapshot_keep_count"' in html


def test_settings_i18n_keys_exist_in_both_locales(client):
    """Every data-i18n key used by the settings block resolves in en + it."""
    import os
    import re

    html = _html(client)
    start = html.index('id="admin-settings"')
    end = html.index('<!-- Tags -->')
    keys = set(re.findall(r'data-i18n="([^"]+)"', html[start:end]))

    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    with open(os.path.join(root, 'app', 'ui', 'static', 'js',
                           'translations.js')) as f:
        js = f.read()
    en_block = js[:js.index('\n    it: {')]
    it_block = js[js.index('\n    it: {'):]
    for key in sorted(keys):
        assert f"{key}:" in en_block, f'missing en translation: {key}'
        assert f"{key}:" in it_block, f'missing it translation: {key}'
