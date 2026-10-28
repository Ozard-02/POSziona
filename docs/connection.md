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
- [x] Commit f722ba2 + `git tag -a v0.1.4` + push main + push tag (CI publishes
      `posziona` + `posziona.exe` on GitHub Releases)

## Rules for event day (read this with 2 machines)

- **Exactly ONE server.** Only one box runs `--mode server` (or `all`).
  Every other box runs `--mode client` (or a plain browser). Two servers =
  two databases = sales split and unrecoverable without merging by hand.
- The login screen tells you which box you are on
  (`This server: CASSA-1 (v0.1.4)`). If both boxes show a server identity,
  one of them must be stopped.
- Blank answers never start a server implicitly: client mode loops until it
  gets a reachable address. Start local servers explicitly (`all`).
- Use ONE address per server consistently (browser sessions/cookies are
  per-origin — the Recent buttons reuse the stored origin).

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

---

## Phase C design (C0, 2026-10-13) — topologies vs UX bar

UX bar: a non-IT operator must go from "powered on" to "selling" with no
network knowledge; at most an IT guy does first setup. Exactly ONE server.

### Scenario matrix (what exists today)

| # | Topology | Today journey | Friction for non-IT |
|---|---|---|---|
| S1 | Same box: `all` (server+window) | Double-click/run → prompt → window | Mode prompt (1/2/3) is jargon; blank/EOF→`all` OK |
| S2 | Same box: server + 2nd client | Terminal A `server`, terminal B `client` → localhost auto-detected | Must open 2 terminals + type flags; hint exists |
| S3 | LAN Wi-Fi: 1 server, N clients | Server prints `Other devices: http://<ip>:5000/`; client `client` mode → UDP discovery menu, or type IP | Discovery unproven on real LAN; typing an IP from one screen to another is the #1 failure (transcription); browser path has no probe → dead page |
| S4 | Hotspot (phone, portable router) | Same as S3, manual IP more likely (AP isolation kills UDP; iPhone hotspots isolate clients entirely) | Typing IPs; no guidance in UI where the address is shown |
| S5 | Remote network (VPN/tunnel) | Manual URL only; terminal probes, browser navigates blind | No documented IT recipe; TLS/cert story undefined |

### Gaps found auditing the flows (2026-10-13, code evidence)

1. **Browser Connect never probes.** Terminal `_discover_or_ask_server`
   TCP-probes + re-prompts; `login.html` Connect just navigates
   (`window.location.href`). Wrong IP = dead page. Fixable: `fetch`
   `<origin>/api/status` first (CORS is open) with timeout, then navigate.
2. **Login fetch has no failure path.** `attemptLogin` has no `.catch` —
   dead server after Connect = silent nothing. Needs an error line.
3. **`alert()` on the login screen** (IP empty/invalid, PIN short/login
   error). Needs the toast treatment (R4b) at the latest here.
4. **No "where do I find the address" guidance.** The server terminal
   prints the URL; nothing tells the operator to read it off that screen
   (or shows it as a QR / `.local` name). Copy-pasteable single line max.
5. **Browser can't discover** (no UDP). Recents cover return visits.
   First contact needs: typed IP (today), or QR/mDNS pairing (C1 research).
6. **Two servers = silent split-brain.** Instance lock protects one DATA_DIR
   only; two boxes each run a server happily. Login identity line helps
   spot it; nothing warns. (C3)
7. **Cart/login survival reviewed OK** (permanent session, 24 h) but
   mid-sale disconnect UX (server dies, client keeps selling?) is
   un-designed. (C4)

### Decision log
- C0: analysis above. C1 research (background): adopt proven pairing +
  reconnect patterns instead of inventing.

### C1 — what comparable systems do (research 2026-10-13)

Discovery (no typing IPs): UDP beacons (stdlib, dies on AP isolation),
mDNS/DNS-SD tap-to-connect (needs daemon/lib, same isolation failure),
**QR pairing** (server shows URL+secret, client scans — survives isolation,
only needs client→server unicast), cloud short-codes (plex.tv/link style —
works anywhere but needs vendor cloud + internet; anti-local-first).
Rule: never multicast-only; ship beacon-list + QR/manual together.
Reconnect: offline outbox (client UUID per sale, retry w/ backoff, server
dedupes) + plain-language banner ("keep selling, N saved, will send").
Thick-client FOSS (UniCenta/Chromis/Floreant) blocks on DB loss — do NOT
copy that. Single-server: no consensus anywhere; guards are claim+warn
(refuse 2nd init when a same-site beacon is live), picker listing ALL
servers, visible terminal count.

### Adopted for POSziona (no new deps, offline-first)
- C2 (now): browser Connect probes `/api/status` via fetch+timeout before
  navigating (CORS is open); login failures get an error line, not silence;
  plain-language address guidance; login `alert()`→inline errors.
- C3 (now): server startup listens briefly for existing beacons and
  prints a plain-language "another server is already on this network"
  warning (refuse nothing — lock still guards one DATA_DIR).
- Later (needs dep/UX design): QR pairing display (qrcode lib), mDNS
  `.local` advertisement, offline outbox + terminal-count header.

---

## C4 — disconnect review (2026-10-13, code evidence)

- Login + cart survive browser restarts (permanent 24 h session cookie).
- Failed checkout keeps the cart and the SAME idempotency key, so retry
  replays instead of double-charging; the double-submit guard now releases
  on failure (was: stuck until reload — fixed with C4).
- SSE uses native `EventSource` → auto-reconnects when the server returns.
- Worst case (server dead mid-sale): red toast, cart intact, operator
  retries or waits. No silent data loss by design. Full offline outbox
  (sell with zero connectivity, sync later) is future work, not needed
  for one-room parties.

## C5 — remote-network recipe (for the IT guy, once per venue)

Goal: a client somewhere else reaches the till. Pick ONE:

1. **VPN (recommended): Tailscale / ZeroTier on both boxes.** Same flat
   network afterwards — server URL is `http://<vpn-ip>:5000/`, and LAN
   discovery usually works too. No firewall surgery.
2. **SSH tunnel:** from the client box,
   `ssh -L 5000:localhost:5000 user@<server>` then open
   `http://127.0.0.1:5000/`. Nothing to install on the server.
3. **Port forward** `5000/tcp` on the venue router to the server box
   (needs router access + ideally a static LAN IP for the server).

Then: on the client, type the URL ONCE in Connect → it becomes a
one-tap Recent button. Notes: plain HTTP (trusted networks only);
 beacons/UDP discovery do not cross subnets — that path is manual URL.

## C5b — firewall one-liners (only the venue LAN, never the internet)

When typing the URL works but discovery does not, one of these is the
usual cause. Port 5000/tcp is the POS page (required); 42137/udp is the
auto-discovery beacon (optional — the client also tries a direct TCP
scan of the local /24 after 5 s of silence, disable that with
`POSZIONA_NO_TCP_SCAN=1`).

- Linux (ufw):
  ```
  sudo ufw allow 5000/tcp
  sudo ufw allow 42137/udp
  ```
- Linux (firewalld):
  ```
  sudo firewall-cmd --add-port=5000/tcp --permanent
  sudo firewall-cmd --add-port=42137/udp --permanent
  sudo firewall-cmd --reload
  ```
- Windows (`posziona.exe`): allow "Private networks" in the Defender
  popup, or from an elevated prompt:
  ```
  netsh advfirewall firewall add rule name="POSziona HTTP" dir=in action=allow protocol=TCP localport=5000
  netsh advfirewall firewall add rule name="Posziona discovery" dir=in action=allow protocol=UDP localport=42137
  ```
- Hotel/guest Wi-Fi with **client isolation**: devices cannot see each
  other even with ports open. Use a phone hotspot (isolation off) or the
  C5 VPN recipe.

## C6 — 2-device live checklist (for the user, needs real LAN)

Use the v0.2.1 release assets (GitHub Releases: `posziona` + `posziona.exe`).

1. Server box: `--mode server`, Admin → System → server
   name (e.g. `CASSA-1`); note the `Other devices on this network` URL.
2. Start a SECOND server on another box on the same Wi-Fi → expect the
   "another POSziona server is already on this network" NOTICE naming
   box 1. Stop the second one.
3. Client box: `client` mode → server appears by tag → select. Also try
   typing the URL once (bare IP, no port) → connects.
4. Browser-only: open `http://<server>:5000/` → login direct; revisit →
   Recent button. Try a WRONG address → friendly error, no dead page.
5. Kill the server mid-sale on a client → red toast, cart intact, retry
   after restart sells exactly once.
6. Report back: discovery found? probe errors clear? warning seen?
