/* Main app JavaScript */
const APP_VERSION = '0.1.0';
const API_BASE = '/api';

// Global app state
const AppState = {
    currentParty: 'default',
    operator: null,
    cart: [],
    discount: null,
    sections: [],
    currentSection: null,
    currentSubsection: null,
    settings: null
};

// Utility functions
function formatCurrency(amount) {
    const currency = AppState.settings?.currency || '€';
    // Guard against null/undefined/NaN — default to 0.00
    const safeAmount = (typeof amount === 'number' && !isNaN(amount)) ? amount : 0;
    return `${currency}${safeAmount.toFixed(2)}`;
}

function showError(message) {
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
    toast.className = 'toast toast-error';
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

// Load app settings on startup
async function loadSettings() {
    try {
        const data = await fetchJSON(`${API_BASE}/settings/?db=${AppState.currentParty}`);
        AppState.settings = data;
    } catch (e) {
        console.error('Failed to load settings:', e);
        AppState.settings = {};
    }
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
    loadSettings();
});
