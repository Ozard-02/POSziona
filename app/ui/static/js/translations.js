/* Posziona translations */
const translations = {
    en: {
        // POS Header
        logout: 'Logout',
        reports: 'Reports',

        // POS Cart
        current_order: 'Current Order',
        subtotal: 'Subtotal:',
        discount: 'Discount:',
        total: 'Total:',
        checkout: 'Checkout',
        discount_btn: 'Discount',
        clear: 'Clear',
        empty_cart: 'Add items to cart first',
        discount_prompt: "Enter discount:\nFor percentage: enter like '10%'\nFor fixed amount: enter like '5' (€5 off total)\nLeave blank to remove discount",
        invalid_discount: 'Invalid discount value',
        checkout_failed: 'Checkout failed',
        stock: 'Stock',
        unavailable: 'Unavailable',

        // Checkout Modal
        checkout_title: 'Checkout',

        // Cash Tender Modal
        cash_title: 'Cash Payment',
        total_due: 'Total Due:',
        amount_received: 'Amount Received (press Enter or click Complete):',
        change_due: 'Change Due:',
        cancel: 'Cancel',
        complete_sale: 'Complete Sale',

        // Receipt
        receipt_title: 'Receipt',
        items: 'Items:',
        total_label: 'Total:',
        payment: 'Payment:',
        tendered: 'Tendered:',
        change: 'Change:',
        order_num: 'Order #:',
        thank_you: 'Thank you for your purchase!',
        print_receipt: 'Print Receipt',
        done: 'Done',
        separator: '---------',
        other: 'Other',
        kitchen_cuisine: 'Cucina',

        // Dashboard
        reports_title: 'Reports',
        back: '← Back',
        print: 'Print',
        summary: 'Summary',
        revenue: 'Total Revenue:',
        orders: 'Total Orders:',
        discounts: 'Total Discounts:',
        items_sold: 'Items Sold',
        product_col: 'Product',
        qty_col: 'Qty',
        unit_price_col: 'Unit Price',
        amount_col: 'Amount',
        no_sales_data: 'No sales data',
        subsections: 'subsections',
        today: 'Today',
        whole_party: 'Whole Party',
        report_date: 'Date (for Today):',
        generate_report: 'Generate Report',
        report_failed: 'Failed to generate report',
        report_date_label: 'Date',
        period_label: 'Period',
        print_summary: 'Print Summary Report',

        // Admin
        admin_panel: 'Admin Panel',
        back_to_pos: '← Back to POS',
        dashboard: 'Dashboard',
        products: 'Products',
        parties: 'Parties & Templates',
        operators: 'Operators',
        settings: 'Settings',
        tags: 'Tags',
        sections: 'Sections',
        add_product: 'Add Product',
        import_csv: 'Import CSV',
        export_csv: 'Export CSV',
        create_tag: 'Create Tag',
        create_party: 'New Party',
        add_operator: 'Add Operator',
        assign: 'Assign',
        save_settings: 'Save Settings',
        settings_scope_note: 'Device settings (printer, language, currency…) apply to all parties; receipt and party settings stay per party.',
        printer_path: 'Printer device path (empty = browser print):',
        printer_baud: 'Printer baud (serial only):',
        printer_cols: 'Printer columns:',
        printer_cut: 'Cut paper after receipt',
        test_print: 'Test print',
        select_party: 'Select party',
        party_default: 'Party default',
        beep_on_sale: 'Beep on add/sale',
        group_party: 'Party',
        group_receipt: 'Receipt',
        group_printer: 'Printer',
        group_pos: 'Counter',
        group_system: 'System',
        receipt_header_label: 'Receipt header:',
        receipt_footer_label: 'Receipt footer:',
        detect_baud: 'Detect',
        detect_baud_ok: 'Printer answers at',
        printer_path_first: 'Enter the printer device path first',
        test_print_ok: 'Test ticket sent',
        printer_failed: 'Printer error',
        active_party: 'Active party:',
        switch_party_confirm: 'Switch party? The current cart will be cleared.',
        settings_saved: 'Settings saved',
        settings_failed: 'Failed to save settings',

        // Product context menu
        edit_price: 'Edit Price',
        set_available: 'Set Available',
        set_unavailable: 'Set Unavailable',
        admin_access_required: 'Admin access required to edit prices',
        change_factory_pin: 'You are using a factory PIN — change it now in Operators below',
        invalid_price: 'Invalid price value',
        price_update_failed: 'Failed to update price',
        availability_update_failed: 'Failed to update availability',
        availability_toggle_mode: 'Availability toggle mode: click a product to toggle',
        set_stock: 'Set Stock',
        invalid_stock: 'Invalid stock value',
        stock_update_failed: 'Failed to update stock',
        enter_new_price: 'Enter new price:',
        enter_new_stock: 'Enter new stock count (leave blank for unlimited):',

        // Startup screen
        startup_title: 'Posziona',
        startup_subtitle: 'Select startup mode',
        mode_local: 'This Server',
        mode_local_desc: 'Log in on the server in the address bar',
        mode_remote: 'Connect to Remote',
        mode_remote_desc: 'Enter a server IP address',
        server_ip_placeholder: '192.168.1.10:5000',
        connect: 'Connect',
        back: 'Back',
        recent_servers: 'Recent servers — tap to reconnect',
        this_server: 'This server',
        server_name_label: 'Server name shown to connecting clients (empty = machine name):',

        // Auth
        login: 'Login',
        admin_login: 'Admin Login',
        operator_name: 'Operator Name',
        pin: 'PIN',
        log_out_confirm: 'Log out?',

        // Settings
        currency_label: 'Currency:',
        language_label: 'Language:',
        default_payment: 'Default Payment Method:',
        none_option: 'None (always ask)',
        cash: 'Cash',
        card: 'Card',
        wallet: 'Digital Wallet',
        tab: 'On Tab',
        total_due: 'Total Due:',
        amount_received: 'Amount Received (press Enter or click Complete):',
        change_due: 'Change Due:',
        enter_amount_received: 'Enter Amount Received',
        process_card: 'Process Card Payment',
        generate_qr: 'Generate QR Code',
        guest_name: 'Guest Name:',
        guest_name_placeholder: 'Enter guest name',
        charge_to_tab: 'Charge to Tab',
        skip_cash_tender: 'Skip cash tender screen (auto-accept exact amount)',
        auto_checkout_label: 'Auto checkout (when both toggles are on, checkout goes straight to receipt)',
        snapshot_interval: 'Snapshot Interval (minutes):',
        split_receipts: 'Print one receipt per section',
        print_recovery_receipt: 'Print recovery receipt (always saved to logs)',
    },

    it: {
        // POS Header
        logout: 'Esci',
        reports: 'Rapporti',

        // POS Cart
        current_order: 'Ordine Attuale',
        subtotal: 'Totale Parziale:',
        discount: 'Sconto:',
        total: 'Totale:',
        checkout: 'Checkout',
        discount_btn: 'Sconto',
        clear: 'Svuota',
        empty_cart: 'Aggiungi prodotti al carrello',
        discount_prompt: "Inserisci sconto:\nPer percentuale: inserisci come '10%'\nPer importo fisso: inserisci come '5' (€5 di sconto)\nLascia vuoto per rimuovere lo sconto",
        invalid_discount: 'Valore sconto non valido',
        checkout_failed: 'Checkout fallito',
        stock: 'Scorta',
        unavailable: 'Non disponibile',

        // Checkout Modal
        checkout_title: 'Checkout',

        // Cash Tender Modal
        cash_title: 'Pagamento Contanti',
        total_due: 'Totale Da Pagare:',
        amount_received: 'Importo Ricevuto (premi Invio o clicca Completa):',
        change_due: 'Resto:',
        cancel: 'Annulla',
        complete_sale: 'Completa Vendita',

        // Receipt
        receipt_title: 'Ricevuta',
        items: 'Prodotti:',
        total_label: 'Totale:',
        payment: 'Pagamento:',
        tendered: 'Versato:',
        change: 'Resto:',
        order_num: 'Ordine N.:',
        thank_you: 'Grazie per l\'acquisto!',
        print_receipt: 'Stampa Ricevuta',
        done: 'Fatto',
        separator: '---------',
        other: 'Altro',
        kitchen_cuisine: 'Cucina',

        // Dashboard
        reports_title: 'Rapporti',
        back: '← Indietro',
        print: 'Stampa',
        summary: 'Riepilogo',
        revenue: 'Ricavo Totale:',
        orders: 'Ordini Totali:',
        discounts: 'Sconti Totali:',
        items_sold: 'Prodotti Venduti',
        product_col: 'Prodotto',
        qty_col: 'Qtà',
        unit_price_col: 'Prezzo Unitario',
        amount_col: 'Totale',
        no_sales_data: 'Nessun dato di vendita',
        subsections: 'sottosezioni',
        today: 'Oggi',
        whole_party: 'Tutta la Festa',
        report_date: 'Data (per Oggi):',
        generate_report: 'Genera Rapporto',
        report_failed: 'Generazione rapporto fallita',
        report_date_label: 'Data',
        period_label: 'Periodo',
        print_summary: 'Stampa Rapporto Sommario',

        // Admin
        admin_panel: 'Pannello Admin',
        back_to_pos: '← Torna al POS',
        dashboard: 'Cruscotto',
        products: 'Prodotti',
        parties: 'Feste & Modelli',
        operators: 'Operatori',
        settings: 'Impostazioni',
        tags: 'Etichette',
        add_product: 'Aggiungi Prodotto',
        import_csv: 'Importa CSV',
        export_csv: 'Esporta CSV',
        create_tag: 'Crea Etichetta',
        create_party: 'Nuova Festa',
        add_operator: 'Aggiungi Operatore',
        assign: 'Assegna',
        save_settings: 'Salva Impostazioni',
        settings_scope_note: 'Le impostazioni dispositivo (stampante, lingua, valuta…) valgono per tutte le feste; scontrino e feste restano per festa.',
        printer_path: 'Percorso stampante (vuoto = stampa browser):',
        printer_baud: 'Baud stampante (solo seriale):',
        printer_cols: 'Colonne stampante:',
        printer_cut: 'Taglia carta dopo lo scontrino',
        test_print: 'Stampa di prova',
        select_party: 'Seleziona festa',
        party_default: 'Default festa',
        beep_on_sale: 'Beep su aggiunta/vendita',
        group_party: 'Festa',
        group_receipt: 'Scontrino',
        group_printer: 'Stampante',
        group_pos: 'Banco',
        group_system: 'Sistema',
        receipt_header_label: 'Intestazione scontrino:',
        receipt_footer_label: 'Piè di pagina scontrino:',
        detect_baud: 'Rileva',
        detect_baud_ok: 'La stampante risponde a',
        printer_path_first: 'Inserisci prima il percorso della stampante',
        test_print_ok: 'Scontrino di prova inviato',
        printer_failed: 'Errore stampante',
        active_party: 'Festa attiva:',
        switch_party_confirm: 'Cambiare festa? Il carrello attuale verrà svuotato.',
        settings_saved: 'Impostazioni salvate',
        settings_failed: 'Salvataggio impostazioni fallito',

        // Product context menu
        edit_price: 'Modifica Prezzo',
        set_available: 'Imposta Disponibile',
        set_unavailable: 'Imposta Non Disponibile',
        admin_access_required: 'Accesso admin richiesto per modificare i prezzi',
        change_factory_pin: 'Stai usando un PIN di fabbrica — cambialo ora in Operatori qui sotto',
        invalid_price: 'Valore prezzo non valido',
        price_update_failed: 'Aggiornamento prezzo fallito',
        availability_update_failed: 'Aggiornamento disponibilità fallito',
        availability_toggle_mode: 'Modalità attiva/disattiva: clicca su un prodotto per toggle',
        set_stock: 'Imposta Scorta',
        invalid_stock: 'Valore scorta non valido',
        stock_update_failed: 'Aggiornamento scorta fallito',
        enter_new_price: 'Inserisci nuovo prezzo:',
        enter_new_stock: 'Inserisci nuova scorta (lascia vuoto per illimitato):',

        // Startup screen
        startup_title: 'Posziona',
        startup_subtitle: 'Seleziona modalità di avvio',
        mode_local: 'Questo Server',
        mode_local_desc: 'Accedi sul server nella barra degli indirizzi',
        mode_remote: 'Connetti a Remoto',
        mode_remote_desc: 'Inserisci un indirizzo IP del server',
        server_ip_placeholder: '192.168.1.10:5000',
        connect: 'Connetti',
        back: 'Indietro',
        recent_servers: 'Server recenti — tocca per riconnetterti',
        this_server: 'Questo server',
        server_name_label: 'Nome server mostrato ai client (vuoto = nome macchina):',

        // Auth
        login: 'Accedi',
        admin_login: 'Accesso Admin',
        operator_name: 'Nome Operatore',
        pin: 'PIN',
        log_out_confirm: 'Uscire?',

        // Settings
        currency_label: 'Valuta:',
        language_label: 'Lingua:',
        default_payment: 'Metodo di Pagamento Predefinito:',
        none_option: 'Nessuno (chiedi sempre)',
        cash: 'Contanti',
        card: 'Carta',
        wallet: 'Portafoglio Digitale',
        tab: 'A Credito',
        total_due: 'Totale Da Pagare:',
        amount_received: 'Importo Ricevuto (premi Invio o clicca Completa):',
        change_due: 'Resto:',
        enter_amount_received: 'Inserisci Importo Ricevuto',
        process_card: 'Processa Pagamento Carta',
        generate_qr: 'Genera Codice QR',
        guest_name: 'Nome Ospite:',
        guest_name_placeholder: 'Inserisci nome ospite',
        charge_to_tab: 'Addebita al Conto',
        skip_cash_tender: 'Salta schermo contanti (accetta importo esatto)',
        auto_checkout_label: 'Checkout automatico',
        snapshot_interval: 'Intervallo Snapshot (minuti):',
        split_receipts: 'Stampa un ricevuta per ogni sezione',
        print_recovery_receipt: 'Stampa ricevuta di recupero (sempre salvata nei log)',
        sections: 'Sezioni',
        subsections: 'sottosezioni',
    },
};

// Get current language from AppState settings or default to 'en'
function getLang() {
    if (typeof AppState !== 'undefined' && AppState.settings && AppState.settings.language) {
        return AppState.settings.language;
    }
    return 'en';
}

// Translation function
function t(key) {
    var lang = getLang();
    if (translations[lang] && translations[lang][key]) {
        return translations[lang][key];
    }
    // Fallback to English
    if (translations.en && translations.en[key]) {
        return translations.en[key];
    }
    return key;
}

// Translate login page elements
function translateLoginPage() {
    var h1 = document.querySelector('.login-screen h1');
    if (h1) h1.textContent = 'Posziona';

    // Startup screen
    var startupTitle = document.getElementById('startup-title');
    if (startupTitle) startupTitle.textContent = t('startup_title');

    var startupSubtitle = document.getElementById('startup-subtitle');
    if (startupSubtitle) startupSubtitle.textContent = t('startup_subtitle');

    var modeLocalLabel = document.querySelector('#mode-local .mode-label');
    if (modeLocalLabel) modeLocalLabel.textContent = t('mode_local');
    var modeLocalDesc = document.querySelector('#mode-local .mode-desc');
    if (modeLocalDesc) modeLocalDesc.textContent = t('mode_local_desc');

    var modeRemoteLabel = document.querySelector('#mode-remote .mode-label');
    if (modeRemoteLabel) modeRemoteLabel.textContent = t('mode_remote');
    var modeRemoteDesc = document.querySelector('#mode-remote .mode-desc');
    if (modeRemoteDesc) modeRemoteDesc.textContent = t('mode_remote_desc');

    var serverInput = document.getElementById('server-input');
    if (serverInput) serverInput.placeholder = t('server_ip_placeholder');

    var connectBtn = document.getElementById('connect-btn');
    if (connectBtn) connectBtn.textContent = t('connect');

    var recentTitleEl = document.getElementById('recent-title');
    if (recentTitleEl) recentTitleEl.textContent = t('recent_servers');

    var backBtn = document.getElementById('back-to-modes');
    if (backBtn) backBtn.textContent = t('back');

    var loginBtn = document.getElementById('login-btn');
    if (loginBtn) loginBtn.textContent = t('login');

    var adminBtn = document.getElementById('admin-login-btn');
    if (adminBtn) adminBtn.textContent = t('admin_login');
}

// Load settings and then translate — call this on page load for POS/Dashboard/Admin
async function initTranslations() {
    if (typeof AppState === 'undefined') {
        window.AppState = { settings: {} };
    }
    try {
        var lang = getLang();
        if (lang === 'en') {
            // Default language, no API call needed
            return;
        }
        var resp = await fetch(`${API_BASE}/settings/?db=default`);
        if (resp.ok) {
            AppState.settings = await resp.json();
        }
    } catch (e) {
        console.error('Failed to load settings for translation:', e);
    }
}
