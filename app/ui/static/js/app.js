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
    alert(message);
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
    return fetch(url, config).then(r => r.json());
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
