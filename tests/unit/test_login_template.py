"""
Login page: remote-connect must not loop on the mode screen.

Regression test for the 2026-10-12 report ("browser keeps looping"):
the Connect button reloaded the server root, which renders the mode
selection again — typing the very IP you were already on looped forever.
"""
import re


def test_login_shell_markers(client):
    """Login shell renders on / and /?mode=local, with connect + reconnect hooks."""
    for path in ('/', '/?mode=local'):
        r = client.get(path)
        assert r.status_code == 200, path
        html = r.get_data(as_text=True)
        assert 'startup-screen' in html
        assert 'login-form-container' in html
    # Connect: same-origin shows login, hop carries ?mode=local (no mode loop).
    assert "?mode=local" in html
    assert "params.get('mode') === 'local'" in html
    assert "target.origin === window.location.origin" in html
    assert "origin + '/?mode=local'" in html  # probe-then-hop, no blind navigate
    # One-tap reconnect: localStorage recent list.
    assert 'id="recent-servers"' in html
    assert 'id="recent-list"' in html
    assert 'posServers' in html
    assert 'recent-title' in html  # label text comes from translations.js
    # Connect probes before hopping (no dead pages), errors inline (no alert).
    assert 'probeThenGo' in html
    assert "'/api/status'" in html or '"/api/status"' in html
    assert 'id="remote-error"' in html
    assert 'id="login-error"' in html
    assert 'alert(' not in html


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
