"""
Login page: remote-connect must not loop on the mode screen.

Regression test for the 2026-10-12 report ("browser keeps looping"):
the Connect button reloaded the server root, which renders the mode
selection again — typing the very IP you were already on looped forever.
"""
import re


def test_login_page_serves_with_mode_param(client):
    """'/?mode=local' renders the same login shell (JS skips the mode screen)."""
    for path in ('/', '/?mode=local'):
        r = client.get(path)
        assert r.status_code == 200, path
        html = r.get_data(as_text=True)
        assert 'startup-screen' in html
        assert 'login-form-container' in html


def test_connect_handler_skips_mode_screen(client):
    """Inline Connect logic: same-origin shows login, hop carries ?mode=local."""
    html = client.get('/').get_data(as_text=True)
    assert "?mode=local" in html
    assert "params.get('mode') === 'local'" in html
    assert "target.origin === window.location.origin" in html
    assert "target.origin + '/?mode=local'" in html


def test_remote_panel_lives_outside_hidden_parent(client):
    """'Connect to Remote' must reveal the IP input (2026-10-12: dead button).

    The #remote-connect panel used to sit inside #startup-screen while its
    handler hid that parent — the input stayed invisible forever.
    """
    html = client.get('/').get_data(as_text=True)
    assert 'id="mode-options"' in html
    assert "modeOptions.classList.add('hidden')" in html
    assert "modeOptions.classList.remove('hidden')" in html
    # Only showLoginForm may hide the whole startup screen.
    assert html.count("startupScreen.classList.add('hidden')") == 1


def test_recent_servers_ui(client):
    """Login page offers one-tap reconnect (localStorage recent list)."""
    html = client.get('/').get_data(as_text=True)
    assert 'id="recent-servers"' in html
    assert 'id="recent-list"' in html
    assert 'posServers' in html
    assert 'recent-title' in html  # label text comes from translations.js


def test_inline_login_js_parses():
    """Syntax smoke for the inline <script> (node --check when available)."""
    import shutil
    import subprocess
    import tempfile
    import os

    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    html_path = os.path.join(root, 'app', 'ui', 'templates', 'login.html')
    with open(html_path) as f:
        html = f.read()
    scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
    assert scripts, 'no inline script found in login.html'
    if shutil.which('node') is None:
        return
    for i, src in enumerate(scripts):
        with tempfile.NamedTemporaryFile('w', suffix='.js',
                                         delete=False) as f:
            f.write(src)
            tmp = f.name
        try:
            subprocess.run(['node', '--check', tmp], check=True,
                           capture_output=True, timeout=30)
        finally:
            os.unlink(tmp)
