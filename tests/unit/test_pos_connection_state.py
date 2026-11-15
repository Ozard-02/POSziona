"""POS offline state: a dropped Wi-Fi must be visible, not a silent pause.

The cart and every sale live on the server, so "no connection" has to be
an unmissable screen state — the failure mode this pins down is an
operator tapping products for ten minutes while nothing is recorded.
"""
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
POS_JS = os.path.join(ROOT, 'app', 'ui', 'static', 'js', 'pos.js')
TRANSLATIONS = os.path.join(ROOT, 'app', 'ui', 'static', 'js', 'translations.js')


def _read(path):
    with open(path) as f:
        return f.read()


def test_sse_open_and_error_drive_the_connection_state():
    src = _read(POS_JS)
    assert "addEventListener('open'" in src
    assert 'setConnected(true)' in src
    assert 'setConnected(false)' in src


def test_offline_banner_and_dead_checkout_button():
    src = _read(POS_JS)
    assert "showBanner(t('connection_lost'))" in src
    assert 'hideBanner()' in src          # cleared when the link comes back
    assert 'checkoutBtn.disabled = !isConnected' in src
    assert "showError(t('connection_lost'))" in src  # guarded click path


def test_connection_lost_message_is_translated_both_ways():
    src = _read(TRANSLATIONS)
    assert src.count('connection_lost:') == 2  # en + it
    assert 'sales are NOT being recorded' in src
    assert 'le vendite NON vengono registrate' in src


def test_pos_js_parses():
    if shutil.which('node') is None:
        return
    for path in (POS_JS, TRANSLATIONS,
                 os.path.join(ROOT, 'app', 'ui', 'static', 'js', 'app.js')):
        subprocess.run(['node', '--check', path], check=True,
                       capture_output=True, timeout=30)
