/* Main app JavaScript */
const APP_VERSION = '0.1.6';
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

// --- Active party: which party DB the sales go to ---
// Single source of truth, shared by pos/admin/dashboard/login.
// localStorage: survives tab/browser restarts (like the 24 h login
// cookie) so the shift setup is still there in the morning. Private
// windows / pywebview private_mode may block it → default then.
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
        if (selected) selectEl.value = selected;
        if (!selectEl.value && selectEl.options.length) selectEl.selectedIndex = 0;
        return (parties || []).map(function(p) { return p.name; });
    });
}

// Switch working party mid-shift: drop the session cart (it belongs to
// the old party's sale — the Flask session cart is not per-db), store
// the new party, reload so every screen re-reads it.
function switchActiveParty(newDb, oldDb) {
    oldDb = oldDb || getActiveDb();
    if (!newDb || newDb === oldDb) return Promise.resolve(false);
    return fetchJSON(API_BASE + '/cart/clear?db=' + encodeURIComponent(oldDb), {method: 'POST'})
        .catch(function() {})
        .then(function() {
            setActiveDb(newDb);
            window.location.reload();
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
            return r.json().then(data => {
                const err = new Error(data.error || `HTTP ${r.status}`);
                err.status = r.status;
                err.data = data;
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
