# UI — "banco pulito" design system

Verified 2026-11-20. The four screens (`login`, `pos`, `dashboard`, `admin`)
share one plain-CSS system in `app/ui/static/css/style.css`. No build step,
no external font, no icon dependency: a till must work offline on an old
machine.

## Principles

- Warm paper canvas, white surfaces, ink text, one deep-green accent.
- Red belongs to destructive actions only. Neutral actions are quiet.
- One type scale, one radius scale, one shadow. Hairlines instead of boxes
  inside boxes.
- Prices, totals and table numbers use tabular figures; numeric columns are
  right-aligned and shrink to their content.
- Motion is 140 ms hover/press plus a visible `:focus-visible` ring. Nothing
  moves because the page scrolled; reduced motion turns all of it off.
- Every screen has a clear empty state. A blank panel is a bug, not a design.

## Tokens

All colours, radii, shadows, spacing and the type stack live in `:root`.
Screens must use the variables, not literals:

| Group | Tokens |
|---|---|
| Surfaces | `--bg`, `--surface`, `--surface-2`, `--surface-3` |
| Text | `--ink`, `--ink-2`, `--ink-3` |
| Lines | `--line`, `--line-strong` |
| Accent | `--accent`, `--accent-hover`, `--accent-soft`, `--accent-ink` |
| States | `--danger`, `--danger-soft`, `--warning`, `--success`, `--success-soft` |
| Shape | `--radius-sm`, `--radius`, `--radius-lg`, `--radius-xl`, `--shadow-1/2/pop` |
| Type | `--font` (system stack), `--mono`, `--ease` |
| Layout | `--topbar-h`, `--rail-w`, `--cart-w` |

Palette: canvas `#f6f5f1`, surface `#ffffff`, ink `#1b1e1c`, accent
`#136f55`, danger `#b42318`.

## App shells

- **POS / reports / admin**: `.app-shell` = fixed viewport column;
  `.app-topbar` (party, operator, actions), then the screen body.
- POS: `.pos-layout` = rail + product grid + cart. The rail and cart scroll
  independently; the page itself does not.
- Reports: `.page` scrolls; `.page-inner` caps the content at 1240px.
- Admin: `.admin-layout` = rail + scrolling content. At 960px and below the
  rail becomes a horizontal strip so tables keep their Actions column.
- Login: `.auth-shell` centres one `.auth-card`; no second dark surface.

## Components

- **Buttons**: `.btn-primary`, `.btn-secondary` (neutral), `.btn-ghost`,
  `.btn-danger`, `.btn-ghost-danger`; sizes `.btn-sm`, `.btn-large`,
  `.btn-block`, `.btn-icon`. A bare `.btn-sm` still renders as a neutral
  button for older generated rows.
- **Forms**: `input/select/textarea` share a 40px height, 8px radius and focus
  ring. Labels are visible above fields; errors sit under the field in
  `.error`.
- **Tables**: `.table-wrap` owns the border, radius and horizontal scroll;
  `.data-table th.num` + `td.num` right-align numeric columns. Do not put a
  second bordered card around the table.
- **Modals**: one system (`.modal` + `.modal-content`), max-height with
  scroll, header/body/footer rhythm. Generated admin dialogs use
  `.dialog-overlay` + `.dialog-content` with the same tokens.
- **Tags**: the client's colours are kept. `readableTextColor()` in `app.js`
  chooses ink or white when no explicit text colour was set.

## Screen contracts

- **POS**: party switcher + real `Online/Offline` pill (SSE state) + operator
  + Reports/Admin/Settings/Logout in the top bar. Rail = sections; grid =
  products (150px min, 104px min height); cart = line items, totals, 50px
  Checkout. Empty states for products and cart.
- **Login**: brand mark, one question ("Where are you selling?"), two mode
  rows, then party/operator/PIN with visible labels. The one-operator case
  hides the operator field, not just the select.
- **Reports**: toolbar, three stat cards, open tabs, items sold, till counts.
  Open tabs is above the sales report because it is money still to collect.
- **Admin**: ACTIVE nav item is real (`aria-current="page"`), page header =
  title + actions right, tables in `.table-wrap`, settings grouped by the
  two real scopes (counter / party).

## Responsive

- POS is designed for 1280-1920 and checked at 1024x768 and 820x1180.
- Login is checked at 390x844; the card uses the available width.
- Reports and admin are checked at 820x1180: stats keep three columns until
  780; the admin rail collapses to a horizontal strip at 960.
- Tables scroll horizontally inside `.table-wrap`, never the whole page.

## Verification

- `venv/bin/pytest tests/ -q` (309 green at the redesign commit).
- `node --check` on every `app/ui/static/js/*.js` and the inline login script.
- Headless screenshots at 1440x900, 1280x900, 1024x768, 820x1180 and
  390x844 against a throwaway `POSZIONA_DATA_DIR`, then inspect for clipping,
  overflow, focus and empty states.
- Stop the throwaway server before running the suite: the LAN discovery tests
  will otherwise find it and fail.
