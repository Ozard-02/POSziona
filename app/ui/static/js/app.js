/* Main app JavaScript */
const APP_VERSION = '0.2.1';
const API_BASE = '/api';

// Global app state (pages keep their own cart/sections; only the operator
// and the merged settings live here).
const AppState = {
    operator: null,
    settings: null
};

// Utility functions
function formatCurrency(amount) {
    const currency = AppState.settings?.currency || '€';
    // Guard against null/undefined/NaN — default to 0.00
    const safeAmount = (typeof amount === 'number' && !isNaN(amount)) ? amount : 0;
    return `${currency}${safeAmount.toFixed(2)}`;
}

// Escape text for interpolation into innerHTML / attribute values.
// Product, section and tag names are free text: a quote in `12" Pizza`
// would otherwise cut an input's value short (and save it truncated),
// and a `<` would be parsed as markup.
function escapeHtml(value) {
    return String(value === null || value === undefined ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Pick ink or white for text on a client-chosen tag colour. Tag colours are
// free text from the admin UI: a light yellow with white text was invisible.
function readableTextColor(hex) {
    var value = String(hex || '').replace('#', '');
    if (value.length === 3) {
        value = value[0] + value[0] + value[1] + value[1] + value[2] + value[2];
    }
    if (!/^[0-9a-f]{6}$/i.test(value)) return '#ffffff';
    function channel(c) {
        var v = parseInt(c, 16) / 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    }
    var luminance = 0.2126 * channel(value.slice(0, 2)) +
        0.7152 * channel(value.slice(2, 4)) +
        0.0722 * channel(value.slice(4, 6));
    return luminance > 0.55 ? '#1b1e1c' : '#ffffff';
}

// --- Active party: which party DB the sales go to ---
// Single source of truth, shared by pos/admin/dashboard/login.
// localStorage: survives tab/browser restarts (like the 24 h login
// cookie) so the shift setup is still there in the morning. Private
// browser windows may block it → default then.
var ACTIVE_DB_KEY = 'posDb';

function _storeGet(key) {
    try {
        return window.localStorage.getItem(key);
    } catch (e) {
        return null;
    }
}

function _storeSet(key, value) {
    try { window.localStorage.setItem(key, value); } catch (e) {}
}

function getActiveDb() {
    var v = _storeGet(ACTIVE_DB_KEY);
    // Mirror of backend validate_db_name: no separators, no traversal.
    if (typeof v === 'string' && v && v.length <= 100 &&
        v.indexOf('/') === -1 && v.indexOf('\\') === -1 &&
        v.indexOf('..') === -1 && v.indexOf('\x00') === -1) {
        return v;
    }
    return 'default';
}

function setActiveDb(name) {
    _storeSet(ACTIVE_DB_KEY, name);
}

// Fill a <select> with the existing parties (by modification date,
// newest first). Resolves to the name list; keeps current selection.
function loadPartyOptions(selectEl, selected) {
    return fetchJSON(API_BASE + '/parties/').then(function(parties) {
        selectEl.innerHTML = '';
        (parties || []).forEach(function(p) {
            var opt = document.createElement('option');
            opt.value = p.name;
            opt.textContent = p.name;
            selectEl.appendChild(opt);
        });
        if (!selectEl.options.length) {
            // First run: no party exists yet. The `default` fallback is
            // the one the server creates on demand, so show it instead of
            // an empty dropdown.
            var fallback = document.createElement('option');
            fallback.value = 'default';
            fallback.textContent = 'default';
            selectEl.appendChild(fallback);
        }
        if (selected) selectEl.value = selected;
        if (!selectEl.value && selectEl.options.length) selectEl.selectedIndex = 0;
        return (parties || []).map(function(p) { return p.name; });
    });
}

// Fill a <select> with the party's ACTIVE operators (login picker).
// The identity is chosen, never guessed from the PIN: two operators who
// share a PIN used to attribute the sale to whoever sorted first.
function loadOperatorOptions(selectEl, party) {
    return fetchJSON(API_BASE + '/auth/operators/roster?db=' + encodeURIComponent(party))
        .then(function(roster) {
            selectEl.innerHTML = '';
            (roster || []).forEach(function(op) {
                var opt = document.createElement('option');
                opt.value = op.id;
                opt.textContent = op.name;
                selectEl.appendChild(opt);
            });
            return roster || [];
        });
}

// Show who is at the till (the header used to show only the party, so on
// a shared screen nobody could tell which operator was selling).
function renderOperatorIdentity() {
    var nodes = document.querySelectorAll('[data-operator-identity]');
    var op = AppState.operator;
    if (!nodes.length || !op) return;
    var label = op.name + (op.role === 'admin' ? ' · admin' : '');
    var initial = String(op.name || '?').trim().charAt(0).toUpperCase();
    nodes.forEach(function(el) {
        el.textContent = label;
        el.dataset.initial = initial;
    });
}

// Switch working party mid-shift: drop the session cart (it belongs to
// the old party's sale — the Flask session cart is not per-db), store the
// new party, then go back to the PIN screen: a login is bound to ONE
// party (operator ids and PINs are per-party), so the operator must
// authenticate again for the new one. The picker preselects it.
function switchActiveParty(newDb, oldDb) {
    oldDb = oldDb || getActiveDb();
    if (!newDb || newDb === oldDb) return Promise.resolve(false);
    return fetchJSON(API_BASE + '/cart/clear?db=' + encodeURIComponent(oldDb), {method: 'POST'})
        .catch(function() {})
        .then(function() {
            setActiveDb(newDb);
            window.location.href = '/?mode=local';
            return true;
        });
}

function showToast(message, kind) {
    // Non-blocking toast: alert() froze the whole kiosk UI until clicked,
    // hiding the sale behind a modal during busy service. Toasts stack
    // (max 5), auto-dismiss after 5s, and click-to-dismiss.
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + kind;
    toast.textContent = message;
    toast.setAttribute('role', 'status');
    toast.addEventListener('click', () => toast.remove());
    container.appendChild(toast);
    while (container.children.length > 5) {
        container.firstChild.remove();
    }
    setTimeout(() => {
        toast.classList.add('toast-hide');
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

function showError(message) {
    showToast(message, 'error');
}

function showSuccess(message) {
    showToast(message, 'success');
}

function showBanner(message) {
    // Persistent, unmissable banner for critical events (e.g. database
    // corruption). Stays until explicitly dismissed — unlike toasts.
    let banner = document.getElementById('alert-banner');
    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'alert-banner';
        banner.setAttribute('role', 'alert');
        const close = document.createElement('button');
        close.id = 'alert-banner-close';
        close.textContent = '✕';
        close.setAttribute('aria-label', 'Dismiss');
        close.addEventListener('click', () => banner.remove());
        const text = document.createElement('span');
        text.id = 'alert-banner-text';
        banner.appendChild(text);
        banner.appendChild(close);
        document.body.prepend(banner);
    }
    document.getElementById('alert-banner-text').textContent = message;
}

function hideBanner() {
    // Clear a banner that no longer applies (e.g. the connection came
    // back). The ✕ button removes it the same way.
    const banner = document.getElementById('alert-banner');
    if (banner) banner.remove();
}

function fetchJSON(url, options = {}) {
    const defaultHeaders = {
        'Content-Type': 'application/json',
    };
    const config = {
        ...options,
        headers: {
            ...defaultHeaders,
            ...options.headers
        }
    };
    return fetch(url, config).then(r => {
        if (!r.ok) {
            // Non-JSON error pages (a bare 413/415 from the server) must not
            // surface as "Unexpected token '<'" to the operator.
            return r.json().catch(function() {
                return { error: `HTTP ${r.status}` };
            }).then(data => {
                const err = new Error(data.error || `HTTP ${r.status}`);
                err.status = r.status;
                err.data = data;
                if (data.code === 'party_mismatch') {
                    // The session was opened on another party: back to the
                    // PIN screen, where the picker preselects the active one.
                    window.location.href = '/?mode=local';
                }
                throw err;
            });
        }
        return r.json();
    });
}

// Check auth status on page load
// Only enforces auth on protected pages (not the login page itself)
async function checkAuth() {
    // Skip auth check on the login page — otherwise we'd get a redirect loop
    if (window.location.pathname === '/' || window.location.pathname === '/login') {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/auth/status`, {
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
            // If the API itself is erroring, don't redirect — let the page load
            // and show an error to the user instead of looping
            console.warn(`Auth status returned HTTP ${response.status}`);
            return;
        }

        const data = await response.json();
        if (!data.logged_in) {
            window.location.href = '/';
        } else {
            AppState.operator = data.operator;
            renderOperatorIdentity();
        }
    } catch (e) {
        // Don't redirect on error — the API being temporarily unavailable
        // should not send the user back to login, causing a reload loop.
        // Instead, log the error so it can be debugged.
        console.error('Auth check failed:', e);
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    checkAuth();
});
