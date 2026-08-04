/* Dashboard / Reports screen JavaScript */
document.addEventListener('DOMContentLoaded', function() {
    const db = 'default';

    const reportType = document.getElementById('report-type');
    const reportDate = document.getElementById('report-date');
    const generateBtn = document.getElementById('generate-report');
    const backBtn = document.getElementById('back-to-pos');
    const printBtn = document.getElementById('print-receipt-btn');
    const printModal = document.getElementById('print-receipt-modal');
    const printReceiptContent = document.getElementById('print-receipt-content');
    const printNowBtn = document.getElementById('print-now-btn');
    const closePrintModalBtn = document.getElementById('close-print-modal');

    const revenueEl = document.getElementById('report-revenue');
    const ordersEl = document.getElementById('report-orders');
    const discountsEl = document.getElementById('report-discounts');
    const reportSummary = document.getElementById('report-summary');
    const reportTables = document.getElementById('report-tables');

    // Set default date to today
    const today = new Date();
    const todayStr = today.toISOString().split('T')[0];
    reportDate.value = todayStr;

    let currentReportData = null;

    // --- Load settings ---
    async function loadSettings() {
        try {
            AppState.settings = await fetchJSON(`${API_BASE}/settings/?db=${db}`);
        } catch (e) {
            console.error('Failed to load settings:', e);
            AppState.settings = {};
        }
        translatePage();
    }

    function translatePage() {
        if (backBtn) backBtn.textContent = t('back');
        if (generateBtn) generateBtn.textContent = t('generate_report');
        if (printBtn) printBtn.textContent = t('print');
    }

    // === Back to POS ===
    if (backBtn) {
        backBtn.addEventListener('click', function() {
            window.location.href = '/pos';
        });
    }

    // === Generate Report ===
    if (generateBtn) {
        generateBtn.addEventListener('click', function() {
            generateReport();
        });
    }

    // === Print receipt modal ===
    if (printBtn) {
        printBtn.addEventListener('click', function() {
            if (currentReportData) {
                printReceiptContent.textContent = buildReportReceipt(currentReportData);
                printModal.classList.remove('hidden');
            }
        });
    }

    if (closePrintModalBtn) {
        closePrintModalBtn.addEventListener('click', function() {
            printModal.classList.add('hidden');
        });
    }

    if (printNowBtn) {
        printNowBtn.addEventListener('click', function() {
            const content = printReceiptContent.textContent;
            const printWindow = window.open('', '_blank');
            printWindow.document.write(
                '<pre>' + content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</pre>'
            );
            printWindow.document.title = 'Posziona - Summary Report';
            printWindow.focus();
            printWindow.print();
            printWindow.close();
        });
    }

    async function generateReport() {
        const type = reportType.value;
        const date = reportDate.value;

        try {
            // Fetch summary
            const summaryUrl = type === 'day'
                ? `${API_BASE}/orders/report/summary?db=${db}&date=${date}`
                : `${API_BASE}/orders/report/summary?db=${db}`;
            const summary = await fetchJSON(summaryUrl);

            // Fetch items sold
            const itemsUrl = type === 'day'
                ? `${API_BASE}/orders/report/items?db=${db}&date=${date}`
                : `${API_BASE}/orders/report/items?db=${db}`;
            const items = await fetchJSON(itemsUrl);

            currentReportData = {
                type: type,
                date: date,
                summary: summary,
                items: items
            };

            renderReport(currentReportData);
        } catch (e) {
            console.error('Report generation failed:', e);
            alert(t('report_failed') + ': ' + (e.message || e));
        }
    }

    function renderReport(data) {
        // Update summary sidebar
        revenueEl.textContent = formatCurrency(data.summary.total_revenue || 0);
        ordersEl.textContent = data.summary.total_orders || 0;
        discountsEl.textContent = formatCurrency(data.summary.total_discounts || 0);

        // Render header
        const periodLabel = data.type === 'day' ? t('today') + ' (' + data.date + ')' : t('whole_party');
        reportSummary.innerHTML = `
            <h3>${t('summary')}: ${periodLabel}</h3>
            <div class="total-row"><span>${t('revenue')}:</span><span>${formatCurrency(data.summary.total_revenue || 0)}</span></div>
            <div class="total-row"><span>${t('orders')}:</span><span>${data.summary.total_orders || 0}</span></div>
            <div class="total-row"><span>${t('discounts')}:</span><span>${formatCurrency(data.summary.total_discounts || 0)}</span></div>
        `;

        // Render items table
        let html = '<h4>' + t('items_sold') + '</h4>';
        if (data.items.length > 0) {
            html += '<table class="data-table"><thead><tr><th>' + t('product_col') + '</th><th>' + t('qty_col') + '</th><th>' + t('unit_price_col') + '</th><th>' + t('amount_col') + '</th></tr></thead><tbody>';
            data.items.forEach(item => {
                html += '<tr><td>' + item.product_name + '</td><td>' + item.total_quantity + '</td><td>' + formatCurrency(item.current_price || 0) + '</td><td>' + formatCurrency(item.total_amount) + '</td></tr>';
            });
            html += '</tbody></table>';
        } else {
            html += '<p class="muted-text">' + t('no_sales_data') + '</p>';
        }

        reportTables.innerHTML = html;
    }

    function buildReportReceipt(data) {
        var lines = [];
        var separator = '=================================';
        lines.push(separator);
        lines.push('        POSZIONA - SUMMARY REPORT    ');
        lines.push(separator);

        var period = data.type === 'day' ? t('report_date_label') + ': ' + data.date : t('period_label') + ': ' + t('whole_party');
        lines.push(period);
        lines.push('');
        lines.push('--- ' + t('summary') + ' ---');
        lines.push(t('revenue') + ' ' + formatCurrency(data.summary.total_revenue || 0));
        lines.push(t('orders') + '  ' + (data.summary.total_orders || 0));
        lines.push(t('discounts') + ' ' + formatCurrency(data.summary.total_discounts || 0));
        lines.push('');
        lines.push('--- ' + t('items_sold') + ' ---');
        if (data.items.length > 0) {
            data.items.forEach(function(item) {
                var qty = item.total_quantity;
                var total = item.total_amount;
                lines.push('  ' + item.product_name +
                           ' x' + qty +
                           ' @ ' + formatCurrency(item.current_price || 0) +
                           ' = ' + formatCurrency(total));
            });
        } else {
            lines.push('  (' + t('no_sales_data') + ')');
        }
        lines.push('');
        lines.push(separator);
        lines.push('  ' + t('thank_you') + '    ');
        lines.push(separator);
        return lines.join('\n');
    }

    // --- Init ---
    loadSettings();
    generateReport();
});
