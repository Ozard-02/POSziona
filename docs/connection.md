# Connection & server-find — frictionless for non-technical staff (v0.1.4)

Goal: on event day, anyone can connect a client to the server with zero
network knowledge. Type once (or tap a discovered server), afterwards one tap.
Target: verify on 2 real devices from the GitHub release assets.

## Problems found live (2026-10-12, Fritz!Box 192.168.178.x)

1. [x] Bare IP opened port 80 (dead page) — fixed 7c: default `:5000` appended.
2. [x] Discovery menu `Enter` didn't pick server 1 — fixed 7c.
3. [x] No reachability check before opening window — fixed 7c: TCP probe + re-prompt.
4. [x] Browser Connect reloaded the mode screen forever — fixed 7d: `?mode=local`.
5. [x] "Connect to Remote" button hid its own panel (input never visible) — fixed 7e.
6. [ ] Auto-find hears nothing (`discover()` → NONE while a 0.1.3 server runs
   here). Suspects: sandbox filters inbound broadcast (known env limit), or an
   old server build on the other box. Cannot fully prove in this sandbox —
   needs the 2-device test below.

## What v0.1.4 adds (this file tracks it)

- [x] **Server tag**: device-global `server_name` setting (empty = machine
      hostname). Editable in Admin → System. Sent in UDP beacons, shown in
      `/api/status`, shown in the terminal picker.
- [x] **Terminal picker shows tags**: `1. CASSA-1 — http://192.168.178.138:5000/ (v0.1.4)`.
- [x] **Browser one-tap reconnect**: login page remembers every server it
      visited (localStorage, max 5) and shows them as big buttons. First visit:
      type IP once. Later: one tap. Works in any browser, no UDP needed.
- [ ] **2-device verification** (by user, with release assets):
  1. Server box: run `posziona --mode server`, set Admin → System → server
     name (e.g. `CASSA-1`), note the `Other devices on this network` URL.
  2. Client box: `posziona --mode client` → server appears by tag → select.
     Fallback: type IP once.
  3. Browser-only: open `http://<server>:5000/` → `?mode=local` login,
     revisit →Recent button.
  4. Report back: discovery found? one-tap reconnect shown?

## Release checklist (v0.1.4)

- [x] Beacon/status/picker/recent code + tests (suite 190 + 1 skip)
- [x] Version bump 0.1.3 → 0.1.4 (pyproject, api/status, app.js, test_api,
      AppImageBuilder.yml, build_exe.bat + `APP_VERSION` single source in config)
- [x] Full suite green
- [ ] Commit + `git tag -a v0.1.4` + push main + push tag (CI publishes
      `posziona` + `posziona.exe` on GitHub Releases)

## Files

- `app/utils/discovery.py` — beacon payload + discover
- `app/services/settings_service.py` — `server_name` device key
- `app/api/__init__.py` — `/api/status`
- `app/api/settings.py` — allowlist
- `app/main.py` — terminal picker
- `app/ui/templates/login.html` — recent servers
- `app/ui/templates/admin.html` — server-name field
- `app/ui/static/js/translations.js` — en/it labels
- `tests/unit/test_discovery.py`, `tests/unit/test_login_template.py`,
  `tests/unit/test_settings_scope.py` or new `test_server_tag.py`
