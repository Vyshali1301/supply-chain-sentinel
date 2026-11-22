// SupplyChain Sentinel Enterprise App Logic

let currentChart = null;
let currentChartPeriod = 'daily';
let activeDisruptionData = null;

function formatUserDateTime(tsStr) {
  if (!tsStr) return 'N/A';
  let str = String(tsStr).trim();

  if (/^\d{2}\s+[A-Za-z]{3}\s+\d{4},\s+\d{2}:\d{2}\s+(AM|PM)$/i.test(str)) {
    return str;
  }

  const ddmmyyyyMatch = str.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4}),?\s+(\d{1,2}):(\d{2})\s*(AM|PM)?$/i);
  if (ddmmyyyyMatch) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const day = String(ddmmyyyyMatch[1]).padStart(2, '0');
    const month = months[parseInt(ddmmyyyyMatch[2]) - 1] || 'Jan';
    const year = ddmmyyyyMatch[3];
    let hour = parseInt(ddmmyyyyMatch[4]);
    const min = String(ddmmyyyyMatch[5]).padStart(2, '0');
    const ampmInput = ddmmyyyyMatch[6] ? ddmmyyyyMatch[6].toUpperCase() : null;

    if (ampmInput) {
      if (hour === 0) hour = 12;
      const formattedHour = String(hour).padStart(2, '0');
      return `${day} ${month} ${year}, ${formattedHour}:${min} ${ampmInput}`;
    } else {
      const ampm = hour >= 12 ? 'PM' : 'AM';
      hour = hour % 12;
      if (hour === 0) hour = 12;
      const formattedHour = String(hour).padStart(2, '0');
      return `${day} ${month} ${year}, ${formattedHour}:${min} ${ampm}`;
    }
  }

  let d;
  if (str.match(/^\d{4}-\d{2}-\d{2}/)) {
    const parts = str.split(/[ T:-]/);
    const yr = parseInt(parts[0]);
    const mo = parseInt(parts[1]) - 1;
    const dy = parseInt(parts[2]);
    const hr = parts[3] ? parseInt(parts[3]) : 0;
    const mn = parts[4] ? parseInt(parts[4]) : 0;
    d = new Date(yr, mo, dy, hr, mn);
  } else {
    d = new Date(str);
  }

  if (isNaN(d.getTime())) return tsStr;

  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const day = String(d.getDate()).padStart(2, '0');
  const month = months[d.getMonth()];
  const year = d.getFullYear();

  let hours = d.getHours();
  const minutes = String(d.getMinutes()).padStart(2, '0');
  const ampm = hours >= 12 ? 'PM' : 'AM';

  hours = hours % 12;
  if (hours === 0) hours = 12;
  const formattedHours = String(hours).padStart(2, '0');

  return `${day} ${month} ${year}, ${formattedHours}:${minutes} ${ampm}`;
}

function formatUserDate(dateStr) {
  if (!dateStr) return 'N/A';
  const str = String(dateStr).trim();

  if (/^\d{2}\s+[A-Za-z]{3}\s+\d{4}$/i.test(str)) {
    return str;
  }

  if (str.match(/^\d{4}-\d{2}-\d{2}/)) {
    const parts = str.split('-');
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const yr = parts[0];
    const mo = months[parseInt(parts[1]) - 1] || parts[1];
    const dy = String(parts[2]).padStart(2, '0');
    return `${dy} ${mo} ${yr}`;
  }

  return formatUserDateTime(dateStr).split(',')[0];
}

document.addEventListener('DOMContentLoaded', () => {
  initDashboard();
  loadAllData();

  // Populate minute options (00 to 59)
  const minSelect = document.getElementById('disruptionMinute');
  if (minSelect && minSelect.options.length === 0) {
    for (let m = 0; m < 60; m++) {
      const val = String(m).padStart(2, '0');
      minSelect.options.add(new Option(val, val));
    }
  }

  // Set default current Date, Hour, Minute, AM/PM
  const dateInput = document.getElementById('disruptionDate');
  if (dateInput) {
    const now = new Date();
    const yr = now.getFullYear();
    const mo = String(now.getMonth() + 1).padStart(2, '0');
    const dy = String(now.getDate()).padStart(2, '0');
    dateInput.value = `${yr}-${mo}-${dy}`;

    let h = now.getHours();
    const ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12;
    if (h === 0) h = 12;
    const hourStr = String(h).padStart(2, '0');
    const minStr = String(now.getMinutes()).padStart(2, '0');

    const hourSelect = document.getElementById('disruptionHour');
    if (hourSelect) hourSelect.value = hourStr;

    if (minSelect) minSelect.value = minStr;

    const ampmSelect = document.getElementById('disruptionAmPm');
    if (ampmSelect) ampmSelect.value = ampm;
  }
});

function getFormattedIntakeTimestamp() {
  const dateInput = document.getElementById('disruptionDate');
  const hourSelect = document.getElementById('disruptionHour');
  const minSelect = document.getElementById('disruptionMinute');
  const ampmSelect = document.getElementById('disruptionAmPm');

  if (dateInput && dateInput.value) {
    const dtStr = dateInput.value;
    let h = parseInt(hourSelect ? hourSelect.value : '12');
    const m = minSelect ? minSelect.value : '00';
    const ampm = ampmSelect ? ampmSelect.value : 'AM';

    if (ampm === 'AM') {
      if (h === 12) h = 0;
    } else {
      if (h !== 12) h += 12;
    }

    const hStr = String(h).padStart(2, '0');
    return `${dtStr} ${hStr}:${m}`;
  }

  const now = new Date();
  const yr = now.getFullYear();
  const mo = String(now.getMonth() + 1).padStart(2, '0');
  const dy = String(now.getDate()).padStart(2, '0');
  const hr = String(now.getHours()).padStart(2, '0');
  const mn = String(now.getMinutes()).padStart(2, '0');
  return `${yr}-${mo}-${dy} ${hr}:${mn}`;
}

// Tab Navigation
function toggleSidebar() {
  const sidebar = document.querySelector('.sidebar');
  if (sidebar) {
    sidebar.classList.toggle('open');
  }
}

function switchTab(tabId) {
  const sidebar = document.querySelector('.sidebar');
  if (sidebar && sidebar.classList.contains('open')) {
    sidebar.classList.remove('open');
  }

  document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

  const activeNav = document.querySelector(`.nav-item[onclick*="'${tabId}'"]`);
  if (activeNav) activeNav.classList.add('active');

  const activeContent = document.getElementById(`tab-${tabId}`);
  if (activeContent) activeContent.classList.add('active');

  if (tabId === 'dashboard') {
    initDashboard();
  } else if (tabId === 'datamanager') {
    loadAllData();
  }
}

function switchTabNav(tabId, subTabId) {
  switchTab(tabId);
  switchSubTab(subTabId);
}

function switchSubTab(subTab) {
  ['products', 'orders', 'shipments', 'suppliers'].forEach(st => {
    const el = document.getElementById(`subtab-${st}`);
    if (el) el.style.display = st === subTab ? 'block' : 'none';
    const btn = document.getElementById(`subtab-btn-${st}`);
    if (btn) {
      if (st === subTab) btn.classList.add('active');
      else btn.classList.remove('active');
    }
  });
}

// Dashboard & Sales Chart Initialization (INR Pricing)
async function initDashboard() {
  try {
    const res = await fetch('/api/dashboard');
    const data = await res.json();

    const m = data.metrics;
    document.getElementById('kpi-sales').innerText = `₹${m.total_sales.toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
    document.getElementById('kpi-inventory').innerText = `${m.total_inventory.toLocaleString()} Units`;
    document.getElementById('kpi-orders').innerText = m.open_orders;
    document.getElementById('kpi-shipments').innerText = m.incoming_shipments;
    document.getElementById('kpi-disruptions').innerText = m.active_disruptions;

    const revRiskEl = document.getElementById('kpi-revenue-risk');
    if (revRiskEl) revRiskEl.innerText = `₹${(m.revenue_at_risk || 0).toLocaleString('en-IN')}`;

    const totalOrdEl = document.getElementById('kpi-total-orders');
    if (totalOrdEl) totalOrdEl.innerText = m.total_orders || 0;

    const pendOrdEl = document.getElementById('kpi-pending-orders');
    if (pendOrdEl) pendOrdEl.innerText = m.pending_orders || 0;

    const procOrdEl = document.getElementById('kpi-processing-orders');
    if (procOrdEl) procOrdEl.innerText = m.processing_orders || 0;

    const compOrdEl = document.getElementById('kpi-completed-orders');
    if (compOrdEl) compOrdEl.innerText = m.completed_orders || 0;

    const riskOrdEl = document.getElementById('kpi-atrisk-orders');
    if (riskOrdEl) riskOrdEl.innerText = m.at_risk_orders || 0;

    const rateEl = document.getElementById('kpi-fulfillment-rate');
    if (rateEl) {
      if (m.fulfillment_rate === 'N/A' || m.fulfillment_rate === undefined || m.fulfillment_rate === null) {
        rateEl.innerText = 'N/A';
      } else {
        rateEl.innerText = `${m.fulfillment_rate}%`;
      }
    }

    const clockEl = document.getElementById('liveClock');
    if (clockEl && m.last_updated) {
      clockEl.innerText = `Last Updated: ${formatUserDateTime(m.last_updated)}`;
    }

    renderSalesChart(data.sales_charts[currentChartPeriod]);
    loadDashboardAlerts();
    loadOperationalActivity();
  } catch (err) {
    console.error('Error loading dashboard:', err);
  }
}

async function loadOperationalActivity() {
  const container = document.getElementById('activityLogContainer');
  if (!container) return;

  try {
    const res = await fetch('/api/activity');
    const data = await res.json();
    const activities = data.activities || [];

    if (activities.length === 0) {
      container.innerHTML = `
        <div style="padding: 1rem; text-align: center; color: var(--text-muted); font-size: 0.8rem;">
          No operational activity logged yet.
        </div>
      `;
      return;
    }

    let html = '';
    activities.forEach(act => {
      html += `
        <div style="padding: 0.5rem 0.65rem; border-bottom: 1px solid var(--border-color); font-size: 0.78rem; display: flex; flex-direction: column; gap: 0.15rem;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 700; color: var(--accent-cyan); font-size: 0.72rem; text-transform: uppercase;">${act.event_type}</span>
            <span style="font-family: var(--font-mono); color: var(--text-muted); font-size: 0.68rem;">${formatUserDateTime(act.created_at)}</span>
          </div>
          <div style="color: var(--text-bright);">${act.description}</div>
        </div>
      `;
    });

    container.innerHTML = html;
  } catch (err) {
    console.error('Error loading activity log:', err);
  }
}

async function loadDashboardAlerts() {
  const container = document.getElementById('dashboardAlertsContainer');
  if (!container) return;

  try {
    const res = await fetch('/api/data');
    const data = await res.json();
    const disruptions = data.disruptions || [];
    
    if (disruptions.length === 0) {
      container.innerHTML = `
        <div style="padding: 1rem; text-align: center; color: var(--text-muted); font-size: 0.8rem;">
          No active disruption alerts logged. System operating normally.
        </div>
      `;
      return;
    }

    let html = '';
    disruptions.slice(0, 4).forEach(d => {
      const isRed = d.status === 'IMPACT DETECTED';
      const isAmber = d.status === 'NEEDS VERIFICATION';
      
      let alertClass = 'green-alert';
      let tagClass = 'text-green';
      let tagText = 'RESOLVED / BUFFER SUFFICIENT';

      if (isRed) {
        alertClass = 'red-alert';
        tagClass = 'text-red';
        tagText = 'CRITICAL SHORTAGE RISK';
      } else if (isAmber) {
        alertClass = 'amber-alert';
        tagClass = 'text-amber';
        tagText = 'DATA CONFLICT HOLD';
      }

      const imp = d.impact_summary_json || {};
      const ext = d.extracted_json || {};

      html += `
        <div class="alert-item ${alertClass}" style="cursor: pointer;" onclick="loadDisruptionReportById(${d.id})">
          <div class="alert-header">
            <span class="alert-tag ${tagClass}">${tagText}</span>
            <span class="alert-time">${formatUserDateTime(d.created_at)}</span>
          </div>
          <div class="alert-body">${ext.product_name_or_sku || 'Product'}: ${ext.delay_days || 0}-Day Delay (${ext.supplier_name || 'Supplier'})</div>
          <div class="alert-footer">${d.status === 'IMPACT DETECTED' ? `Shortage: ${imp.inventory_shortage || 0} Units | Order Risk: ₹${(imp.order_value_at_risk || 0).toLocaleString('en-IN')}` : (d.status === 'NO IMPACT' ? `Buffer: +${imp.remaining_buffer || 0} Units | Zero SLA Delay` : `Conflict: Data Verification Required`)}</div>
        </div>
      `;
    });

    container.innerHTML = html;
  } catch (err) {
    console.error('Error loading dashboard alerts:', err);
  }
}

async function loadDisruptionReportById(dId) {
  try {
    const res = await fetch(`/api/disruptions/${dId}`);
    const data = await res.json();
    if (data.id) {
      // Normalise DB field names to match the renderReportView contract
      const impJson = data.impact_summary_json || {};
      activeDisruptionData = {
        disruption_id: data.id,
        raw_text: data.raw_text,
        extracted_info: data.extracted_json || {},
        status: data.status,
        evidence: data.evidence_json || {},
        impact_summary: impJson,
        response_options: impJson.response_options || [],
        ai_recommendation: impJson.ai_recommendation || '',
        trace: data.trace_json || { nodes: [], edges: [] },
        human_decision: data.human_decision,
        mitigation_status: data.mitigation_status,
        mitigation_cost: data.mitigation_cost,
        mitigation_notes: data.mitigation_notes,
        created_at: data.created_at
      };
      renderReportView(activeDisruptionData);
      renderImpactTrace(activeDisruptionData.trace);
      switchTab('report');
    }
  } catch (err) {
    console.error('Error fetching disruption report:', err);
  }
}

function setChartPeriod(period) {
  currentChartPeriod = period;
  ['daily', 'weekly', 'monthly'].forEach(p => {
    const b = document.getElementById(`btn-${p}`);
    if (b) {
      if (p === period) b.classList.add('active');
      else b.classList.remove('active');
    }
  });
  initDashboard();
}

function renderSalesChart(chartData) {
  const canvas = document.getElementById('salesChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (currentChart) {
    currentChart.destroy();
  }

  const gradient = ctx.createLinearGradient(0, 0, 0, 300);
  gradient.addColorStop(0, 'rgba(2, 132, 199, 0.3)');
  gradient.addColorStop(1, 'rgba(2, 132, 199, 0.0)');

  currentChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: chartData.labels,
      datasets: [{
        label: 'Sales Revenue (₹ INR)',
        data: chartData.data,
        borderColor: '#0284c7',
        borderWidth: 2.5,
        backgroundColor: gradient,
        fill: true,
        tension: 0.3,
        pointBackgroundColor: '#38bdf8',
        pointRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { color: '#94a3b8' }
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { color: '#94a3b8' }
        }
      }
    }
  });
}

// Operational Test Case Presets
function loadScenario(num) {
  const input = document.getElementById('rawDisruptionInput');
  if (num === 1) {
    input.value = "ABC supplier informed us that 500 Laptop X units will be delayed by 5 days because of a transportation problem.";
  } else if (num === 2) {
    input.value = "Supplier FastFab announced a 3-day delay on Ergonomic Chair Pro shipments due to port congestion.";
  } else if (num === 3) {
    input.value = "Supplier Global Microchip Co reports 1000 units of Laptop X delayed by 10 days.";
  }
}

// Submit Disruption Analysis
async function submitDisruptionAnalysis() {
  const rawText = document.getElementById('rawDisruptionInput').value.trim();
  if (!rawText) {
    alert('Please enter or select a disruption message first.');
    return;
  }

  const btn = event.target;
  const originalText = btn.innerHTML;
  btn.innerHTML = 'Running Impact Engine...';
  btn.disabled = true;

  try {
    const formattedTs = getFormattedIntakeTimestamp();
    const res = await fetch('/api/disruptions/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: rawText, timestamp: formattedTs })
    });
    const data = await res.json();
    data.intake_timestamp = formattedTs;
    activeDisruptionData = data;

    renderReportView(data);
    renderImpactTrace(data.trace);
    switchTab('report');
    initDashboard();

  } catch (err) {
    alert('Error executing disruption assessment: ' + err.message);
  } finally {
    btn.innerHTML = originalText;
    btn.disabled = false;
  }
}

// Render Structured Disruption Assessment Report View
function renderReportView(data) {
  const statusBadgeContainer = document.getElementById('reportStatusBadge');
  const container = document.getElementById('reportContentContainer');

  let badgeClass = 'badge-amber';
  if (data.status === 'IMPACT DETECTED') badgeClass = 'badge-red';
  else if (data.status === 'NO IMPACT') badgeClass = 'badge-green';

  statusBadgeContainer.innerHTML = `<span class="status-badge ${badgeClass}">${data.status}</span>`;

  const ext = data.extracted_info || {};
  const ev = data.evidence || {};
  const imp = data.impact_summary || {};
  const options = data.response_options || [];
  const intakeTs = formatUserDateTime(data.intake_timestamp || data.created_at || getFormattedIntakeTimestamp());

  let html = `
    <!-- DISRUPTION SIGNAL INTAKE -->
    <div style="background: var(--bg-input); border: 1px solid var(--border-color); border-radius: 4px; padding: 0.85rem 1rem; margin-bottom: 1rem;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
        <div style="font-size: 0.68rem; font-weight: 700; color: var(--accent-cyan); text-transform: uppercase; letter-spacing: 0.05em;">
          DISRUPTION SIGNAL RECEIVED
        </div>
        <div style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted);">
          ${intakeTs}
        </div>
      </div>
      <div style="font-family: var(--font-mono); font-size: 0.88rem; color: var(--text-bright); font-style: italic;">
        "${data.raw_text}"
      </div>
    </div>

    <!-- INCIDENT SUMMARY & MASTER DATA ATTRIBUTION GRID -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-bottom: 1.25rem;">
      <!-- Extracted Attributes -->
      <div style="background: var(--bg-input); border: 1px solid var(--border-color); border-radius: 4px; padding: 1rem;">
        <div style="font-size: 0.72rem; font-weight: 700; color: var(--accent-cyan); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.65rem;">
          EXTRACTED DISRUPTION ATTRIBUTES
        </div>
        <div style="display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.82rem;">
          <div><strong style="color: var(--text-muted);">Supplier:</strong> ${ext.supplier_name || 'N/A'}</div>
          <div><strong style="color: var(--text-muted);">Product / SKU:</strong> ${ext.product_name_or_sku || 'N/A'}</div>
          <div><strong style="color: var(--text-muted);">Affected Qty:</strong> ${ext.quantity_affected || 0} units</div>
          <div><strong style="color: var(--text-muted);">Delay Duration:</strong> ${ext.delay_days || 0} days</div>
          <div><strong style="color: var(--text-muted);">Disruption Reason:</strong> ${ext.reason || 'N/A'}</div>
        </div>
      </div>

      <!-- Master Data Match & Attribution -->
      <div style="background: var(--bg-input); border: 1px solid var(--border-color); border-radius: 4px; padding: 1rem;">
        <div style="font-size: 0.72rem; font-weight: 700; color: var(--accent-cyan); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.65rem;">
          MASTER DATA MATCHING & ATTRIBUTION
        </div>
        <div style="display: flex; flex-direction: column; gap: 0.5rem; font-size: 0.82rem;">
          <div>
            <strong>Supplier Match:</strong> ${ev.supplier_match ? ev.supplier_match.value : 'Not Found'}
            <div style="font-size: 0.7rem; color: var(--text-muted);">Source: ${ev.supplier_match ? ev.supplier_match.source : 'N/A'}</div>
          </div>
          <div>
            <strong>Product Match:</strong> ${ev.product_match ? ev.product_match.value : 'Not Found'}
            <div style="font-size: 0.7rem; color: var(--text-muted);">Source: ${ev.product_match ? ev.product_match.source : 'N/A'}</div>
          </div>
          <div>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <div>
                <strong>Active Shipment:</strong> ${ev.shipment_match ? ev.shipment_match.value : 'None'}
                <div style="font-size: 0.7rem; color: var(--text-muted);">Source: ${ev.shipment_match ? ev.shipment_match.source : 'N/A'}</div>
              </div>
              ${ev.shipment_match && ev.shipment_match.shipment_id ? `
                <button class="btn btn-green btn-sm" onclick="openReceiveGoodsModal(${ev.shipment_match.shipment_id}, '${ev.shipment_match.shipment_code}', '${(ev.product_match ? ev.product_match.value : 'Product').replace(/'/g, "\\'")}', ${ev.shipment_match.quantity || 500}, ${ev.shipment_match.received_quantity || 0}, ${ev.shipment_match.remaining_qty || 500})">
                  📦 Receive Goods
                </button>
              ` : ''}
            </div>
          </div>
          <div>
            <strong>Inventory Master:</strong> ${ev.inventory_match ? ev.inventory_match.value : 'N/A'}
            <div style="font-size: 0.7rem; color: var(--text-muted);">Source: ${ev.inventory_match ? ev.inventory_match.source : 'N/A'}</div>
          </div>
        </div>
      </div>
    </div>
  `;

  // DATA CONFLICT Callout Box when NEEDS VERIFICATION occurs
  if (ev.contradiction_found && ev.contradiction_items && ev.contradiction_items.length > 0) {
    html += `
      <div style="background: var(--bg-amber); border: 1px solid var(--border-amber); border-radius: 4px; padding: 1rem; margin-bottom: 1.25rem;">
        <div style="font-size: 0.85rem; font-weight: 800; color: var(--color-amber); letter-spacing: 0.05em; margin-bottom: 0.5rem;">
          ⚠️ DATA CONFLICT DETECTED — IMPACT ANALYSIS PAUSED
        </div>
        <p style="font-size: 0.82rem; color: var(--text-main); margin-bottom: 0.75rem;">
          Impact assessment is paused pending manual verification of conflicting records:
        </p>
        <div style="display: flex; flex-direction: column; gap: 0.65rem;">
          ${ev.contradiction_items.map(c => `
            <div style="background: rgba(0,0,0,0.3); padding: 0.75rem; border-radius: 4px; border-left: 3px solid var(--color-amber); font-size: 0.82rem;">
              <strong style="color: var(--color-amber); font-size: 0.85rem;">${c.issue}</strong>
              <div style="margin-top: 0.25rem;"><strong>DISRUPTION CLAIM:</strong> ${c.disruption_claim}</div>
              <div><strong>SYSTEM RECORD:</strong> ${c.db_record}</div>
              <div style="color: var(--text-muted); font-size: 0.75rem; margin-top: 0.2rem;">${c.reason}</div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  // NO IMPACT Result Display
  if (data.status === 'NO IMPACT') {
    html += `
      <div style="background: var(--bg-green); border: 1px solid var(--border-green); border-radius: 4px; padding: 1.1rem; margin-bottom: 1.25rem;">
        <div style="font-size: 0.9rem; font-weight: 800; color: var(--color-green); letter-spacing: 0.04em; margin-bottom: 0.35rem;">
          ✓ NO BUSINESS IMPACT — FULFILLMENT SCHEDULE PROTECTED
        </div>
        <p style="font-size: 0.85rem; color: var(--text-main); line-height: 1.4; margin-bottom: 0.85rem;">
          Current inventory on hand is fully sufficient to satisfy all open customer orders until the delayed shipment arrives.
        </p>

        <!-- NO IMPACT Buffer Calculation Table -->
        <div style="background: var(--bg-input); border-radius: 4px; padding: 0.85rem; display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0.85rem; border: 1px solid var(--border-color);">
          <div>
            <div style="font-size: 0.68rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase;">Available Stock</div>
            <div style="font-family: var(--font-mono); font-size: 1.2rem; font-weight: 700; color: var(--text-bright);">${imp.current_stock || 0} Units</div>
            <div style="font-size: 0.68rem; color: var(--text-muted);">Warehouse Master</div>
          </div>
          <div>
            <div style="font-size: 0.68rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase;">Open Demand</div>
            <div style="font-family: var(--font-mono); font-size: 1.2rem; font-weight: 700; color: var(--text-bright);">${imp.open_order_demand || 0} Units</div>
            <div style="font-size: 0.68rem; color: var(--text-muted);">Customer Orders DB</div>
          </div>
          <div>
            <div style="font-size: 0.68rem; color: var(--text-muted); font-weight: 700; text-transform: uppercase;">Remaining Stock Buffer</div>
            <div style="font-family: var(--font-mono); font-size: 1.2rem; font-weight: 700; color: var(--color-green);">+${imp.remaining_buffer || 0} Units</div>
            <div style="font-size: 0.68rem; color: var(--color-green);">Zero Delivery Risk</div>
          </div>
        </div>
      </div>
    `;
  } else if (data.status === 'IMPACT DETECTED') {
    html += `
      <!-- BUSINESS CONSEQUENCE SECTION -->
      <div style="margin-bottom: 1.25rem;">
        <div style="font-size: 0.82rem; font-weight: 800; color: var(--color-red); letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 0.6rem;">
          BUSINESS CONSEQUENCE & FULFILLMENT RISK
        </div>
        <div class="consequence-grid">
          <div class="consequence-card critical">
            <div class="consequence-title">INVENTORY SHORTAGE</div>
            <div class="consequence-num text-red">${imp.inventory_shortage || 0} UNITS SHORT</div>
            <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.2rem;">
              (Stock: ${imp.current_stock || 0} / Demand: ${imp.open_order_demand || 0})
            </div>
          </div>
          <div class="consequence-card warning">
            <div class="consequence-title">AFFECTED ORDERS</div>
            <div class="consequence-num text-amber">${(imp.affected_customer_orders || []).length} ORDERS</div>
            <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.2rem;">
              ${imp.units_at_risk || 0} Units Slipping
            </div>
          </div>
          <div class="consequence-card critical">
            <div class="consequence-title">ORDER VALUE AT RISK</div>
            <div class="consequence-num text-red">₹${(imp.order_value_at_risk || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</div>
            <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.2rem;">
              Pending Revenue Slippage
            </div>
          </div>
          <div class="consequence-card">
            <div class="consequence-title">ESTIMATED DELAY</div>
            <div class="consequence-num text-blue">+${ext.delay_days || 5} DAYS</div>
            <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.2rem;">
              Supplier Delay
            </div>
          </div>
        </div>

        <!-- Affected Customer Accounts Table -->
        <div style="background: var(--bg-input); border: 1px solid var(--border-color); border-radius: 4px; padding: 0.85rem; margin-top: 0.75rem;">
          <div style="font-size: 0.72rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 0.5rem;">
            AFFECTED CUSTOMER ACCOUNTS & SLIPPING DELIVERIES
          </div>
          <div style="display: flex; flex-direction: column; gap: 0.4rem;">
            ${(imp.affected_customer_orders || []).map(o => `
              <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.2); padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.82rem;">
                <span><strong style="color: var(--text-bright);">${o.order_number}</strong> — ${o.customer} (${o.qty_unfulfilled} units short)</span>
                <span style="font-family: var(--font-mono); color: var(--color-amber); font-weight: 700;">₹${o.value.toLocaleString('en-IN')} | +${o.delay_days} Days</span>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    `;
  }

  // MITIGATION RESPONSE MATRIX & TRADE-OFF ANALYSIS
  html += `
    <div style="margin-top: 1.25rem;">
      <div style="font-size: 0.82rem; font-weight: 800; color: var(--accent-cyan); letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 0.6rem;">
        MITIGATION RESPONSE MATRIX & TRADE-OFF ANALYSIS
      </div>
      <div style="overflow-x: auto;">
        <table class="ops-table">
          <thead>
            <tr>
              <th>Response Strategy</th>
              <th>Action Plan</th>
              <th>Estimated Cost</th>
              <th>Orders Protected</th>
              <th>Customer Impact</th>
              <th>Assumptions & Trade-offs</th>
            </tr>
          </thead>
          <tbody>
            ${options.map(opt => `
              <tr>
                <td><strong style="color: var(--accent-cyan);">${opt.name}</strong></td>
                <td>${opt.action}</td>
                <td><span style="font-family: var(--font-mono); color: var(--color-red); font-weight: 700;">${opt.cost}</span></td>
                <td><span style="color: var(--color-green); font-weight: 700;">${opt.orders_protected || 'N/A'}</span></td>
                <td>${opt.customer_impact || 'N/A'}</td>
                <td style="font-size: 0.75rem; color: var(--text-muted);">${opt.trade_off || opt.assumption || 'N/A'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>

    <!-- AI RECOMMENDATION & HUMAN APPROVAL CONSOLE -->
    <div style="margin-top: 1.25rem; background: var(--bg-input); border: 1px solid var(--accent-blue); border-radius: 4px; padding: 1rem;">
      <div style="font-size: 0.7rem; font-weight: 700; color: var(--accent-cyan); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.35rem;">
        RECOMMENDED RESPONSE (AI-ASSISTED ANALYSIS)
      </div>
      <div style="font-size: 0.95rem; font-weight: 700; color: var(--text-bright); margin-bottom: 0.65rem;">
        ${data.ai_recommendation || 'Expedite Air Cargo'}
      </div>

      <div style="border-top: 1px solid var(--border-color); padding-top: 0.75rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem;">
        <div>
          <span style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted);">DECISION:</span>
          <span id="humanDecisionStatus" style="font-family: var(--font-mono); font-weight: 800; color: var(--color-green); margin-left: 0.4rem;">
            ${data.human_decision || 'Pending Review'}
          </span>
          <span style="margin-left: 0.75rem; font-size: 0.75rem; font-weight: 700; color: var(--text-muted);">LIFECYCLE:</span>
          <span style="font-family: var(--font-mono); font-weight: 800; color: ${data.mitigation_status === 'In Progress' ? 'var(--accent-cyan)' : (data.mitigation_status === 'Resolved' ? 'var(--color-green)' : 'var(--text-muted)')}; margin-left: 0.4rem;">
            ${data.mitigation_status || 'Pending Review'}
          </span>
          ${data.mitigation_cost ? `<span style="margin-left: 0.75rem; font-size: 0.75rem; color: var(--accent-rose); font-weight: 700;">COST: ₹${Number(data.mitigation_cost).toLocaleString('en-IN', {minimumFractionDigits: 2})}</span>` : ''}
        </div>

        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
          <button class="btn btn-green btn-sm" onclick="commitHumanDecision(${data.disruption_id}, 'Approved: Expedite Air Freight')">APPROVE ACTION</button>
          <button class="btn btn-outline btn-sm" onclick="commitHumanDecision(${data.disruption_id}, 'Approved: Split Shipment')">MODIFY STRATEGY</button>
          <button class="btn btn-danger btn-sm" onclick="commitHumanDecision(${data.disruption_id}, 'Rejected / Standby')">REJECT / STANDBY</button>
        </div>
      </div>
      ${data.mitigation_notes ? `
        <div style="margin-top: 0.6rem; padding: 0.5rem 0.75rem; background: rgba(0,0,0,0.3); border-left: 3px solid var(--accent-cyan); font-size: 0.75rem; color: var(--text-muted); line-height: 1.4;">
          <strong>Operational Detail:</strong> ${data.mitigation_notes}
        </div>
      ` : ''}
    </div>
  `;

  container.innerHTML = html;
}

// Render Impact Trace Visual Pipeline
function renderImpactTrace(trace) {
  const container = document.getElementById('traceContainer');
  if (!trace || !trace.nodes || trace.nodes.length === 0) {
    container.innerHTML = `<p style="color: var(--text-muted); text-align: center; width: 100%;">No trace pipeline available.</p>`;
    return;
  }

  let html = '';
  trace.nodes.forEach((node, idx) => {
    html += `
      <div class="trace-node" onclick="showNodeDetail(${idx})">
        <div class="trace-node-type">${node.type}</div>
        <div class="trace-node-label">${node.label}</div>
        <div style="font-size: 0.68rem; color: var(--accent-cyan); margin-top: 0.25rem;">Inspect</div>
      </div>
    `;
    if (idx < trace.nodes.length - 1) {
      html += `<div class="trace-arrow">➔</div>`;
    }
  });

  container.innerHTML = html;
}

function showNodeDetail(idx) {
  if (!activeDisruptionData || !activeDisruptionData.trace || !activeDisruptionData.trace.nodes) return;
  const node = activeDisruptionData.trace.nodes[idx];
  if (!node) return;

  const box = document.getElementById('nodeDetailBox');
  const title = document.getElementById('nodeDetailTitle');
  const content = document.getElementById('nodeDetailContent');

  title.innerText = `Node Payload Inspection: ${node.label}`;
  
  if (node.details) {
    let detailsHtml = '<ul style="list-style: none; display: flex; flex-direction: column; gap: 0.35rem;">';
    for (const [k, v] of Object.entries(node.details)) {
      detailsHtml += `<li><strong style="color: var(--accent-cyan);">${k}:</strong> ${v}</li>`;
    }
    detailsHtml += '</ul>';
    content.innerHTML = detailsHtml;
  } else {
    content.innerText = `Node Type: ${node.type} | ID: ${node.id}`;
  }

  box.style.display = 'block';
}

// Grounded Question Answering Handlers
async function submitQAQuery() {
  const input = document.getElementById('qaInput');
  const query = input.value.trim();
  if (!query) return;

  const box = document.getElementById('qaAnswerBox');
  const text = document.getElementById('qaAnswerText');
  box.style.display = 'block';
  text.innerText = 'Querying system database records...';

  try {
    const res = await fetch('/api/qa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: query })
    });
    const data = await res.json();
    text.innerText = data.answer || 'Insufficient data in database to answer reliably.';
  } catch (err) {
    text.innerText = 'Error processing query: ' + err.message;
  }
}

function askPresetQA(questionText) {
  document.getElementById('qaInput').value = questionText;
  submitQAQuery();
}

// Commit Human Decision
async function commitHumanDecision(dId, decisionText) {
  try {
    const res = await fetch(`/api/disruptions/${dId}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision: decisionText })
    });
    const data = await res.json();
    if (data.success) {
      const decisionEl = document.getElementById('humanDecisionStatus');
      if (decisionEl) decisionEl.innerText = decisionText;

      if (data.already_applied) {
        alert(`Strategy already in progress: ${decisionText}\nOperational state was already committed.`);
      } else {
        alert(`Decision Implemented: ${decisionText}\nLifecycle: ${data.mitigation_status || 'In Progress'}\nMitigation Cost: ₹${(data.mitigation_cost || 0).toLocaleString('en-IN')}\nRevised ETA: ${data.revised_eta || 'Preserved'}`);
      }

      // Re-fetch disruption report to refresh visual Impact Trace and details
      try {
        const repRes = await fetch(`/api/disruptions/${dId}`);
        if (repRes.ok) {
          const dbDisruption = await repRes.json();
          // Normalise DB field names to match renderReportView contract
          const impJson = dbDisruption.impact_summary_json || {};
          activeDisruptionData = {
            disruption_id: dbDisruption.id,
            raw_text: dbDisruption.raw_text,
            extracted_info: dbDisruption.extracted_json || {},
            status: dbDisruption.status,
            evidence: dbDisruption.evidence_json || {},
            impact_summary: impJson,
            response_options: impJson.response_options || [],
            ai_recommendation: impJson.ai_recommendation || '',
            trace: dbDisruption.trace_json || { nodes: [], edges: [] },
            human_decision: dbDisruption.human_decision,
            mitigation_status: dbDisruption.mitigation_status,
            mitigation_cost: dbDisruption.mitigation_cost,
            mitigation_notes: dbDisruption.mitigation_notes,
            created_at: dbDisruption.created_at
          };
          renderReportView(activeDisruptionData);
          renderImpactTrace(activeDisruptionData.trace);
        }
      } catch (e) {
        console.warn('Could not refresh disruption report trace:', e);
      }

      initDashboard();
      loadAllData();
    } else {
      alert('Error updating decision: ' + (data.error || 'Failed'));
    }
  } catch (err) {
    alert('Failed to record decision: ' + err.message);
  }
}

// Load Master Data Tables (INR Pricing)
async function loadAllData() {
  try {
    const res = await fetch('/api/data');
    const data = await res.json();

    // Map product stocks for order fulfillment helper
    const productStockMap = {};
    (data.products || []).forEach(p => {
      productStockMap[p.id] = p.current_stock;
    });

    // Products
    const prodBody = document.getElementById('tbl-products-body');
    prodBody.innerHTML = data.products.map(p => `
      <tr>
        <td>${p.id}</td>
        <td><strong>${p.sku}</strong></td>
        <td>${p.name}</td>
        <td>${p.category}</td>
        <td>₹${p.unit_cost.toLocaleString('en-IN', {minimumFractionDigits:2})}</td>
        <td>₹${p.selling_price.toLocaleString('en-IN', {minimumFractionDigits:2})}</td>
        <td>
          <input type="number" value="${p.current_stock}" onchange="updateDataField('products', ${p.id}, 'current_stock', this.value)">
        </td>
        <td>${p.safety_stock}</td>
        <td>
          <button class="btn btn-outline" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="updateDataField('products', ${p.id}, 'current_stock', 500)">Set Stock 500</button>
        </td>
      </tr>
    `).join('');

    // Orders
    const ordBody = document.getElementById('tbl-orders-body');
    ordBody.innerHTML = data.customer_orders.map(o => {
      const fulfilled = o.quantity_fulfilled || 0;
      const remaining = o.quantity_remaining !== undefined ? o.quantity_remaining : Math.max(0, o.quantity_ordered - fulfilled);
      const availStock = productStockMap[o.product_id] || 0;
      const fulfillPct = o.quantity_ordered > 0 ? Math.round((fulfilled / o.quantity_ordered) * 100) : 100;
      let badgeClass = 'badge-verification';
      if (o.status === 'Completed') badgeClass = 'badge-noimpact';
      else if (o.status === 'Partially Fulfilled') badgeClass = 'badge-amber';
      else if (o.status === 'Delayed' || o.status === 'At Risk') badgeClass = 'badge-red';

      return `
        <tr>
          <td><strong>${o.order_number}</strong></td>
          <td>${o.customer_name}</td>
          <td>${o.product_name}</td>
          <td>${o.quantity_ordered} units</td>
          <td style="color: var(--accent-emerald); font-weight: 600;">${fulfilled} units</td>
          <td style="color: var(--accent-rose); font-weight: 600;">${remaining} units</td>
          <td>₹${o.total_price.toLocaleString('en-IN')}</td>
          <td>${formatUserDate(o.order_date)}</td>
          <td>${formatUserDate(o.expected_ship_date)}</td>
          <td>
            <span class="badge ${badgeClass}">${o.status}</span>
            <div style="font-size: 0.72rem; color: var(--accent-cyan); font-weight: 700; margin-top: 0.2rem;">${fulfillPct}% Fulfilled</div>
            ${o.sla_status && o.sla_status !== 'On Schedule' ? `<div style="font-size: 0.68rem; color: var(--color-green); font-weight: 700; margin-top: 0.2rem;">🛡️ ${o.sla_status}</div>` : ''}
          </td>
          <td>
            ${remaining > 0 ? `
              <button class="btn btn-primary" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="openFulfillOrderModal(${o.id}, '${o.order_number}', '${o.customer_name.replace(/'/g, "\\'")}', '${o.product_name.replace(/'/g, "\\'")}', ${o.quantity_ordered}, ${fulfilled}, ${remaining}, ${availStock})">
                Fulfill Order
              </button>
            ` : `<span style="font-size: 0.75rem; color: var(--color-green); font-weight: 700;">✓ Fulfilled</span>`}
          </td>
        </tr>
      `;
    }).join('');

    // Shipments
    const shpBody = document.getElementById('tbl-shipments-body');
    const validStatuses = [
      'Scheduled', 
      'In Transit', 
      'In Transit (Expedited Air)', 
      'In Transit (Hybrid Air/Ocean)', 
      'Delayed', 
      'Partially Received', 
      'Received'
    ];
    shpBody.innerHTML = data.shipments.map(s => {
      const rec = s.received_quantity || 0;
      const rem = s.remaining_quantity !== undefined ? s.remaining_quantity : (s.quantity - rec);
      const currentStatuses = [...validStatuses];
      if (s.status && !currentStatuses.includes(s.status)) {
        currentStatuses.push(s.status);
      }
      const statusOptions = currentStatuses.map(st => `<option value="${st}" ${s.status === st ? 'selected' : ''}>${st}</option>`).join('');
      const isDelayed = s.status === 'Delayed';
      const isExpedited = s.status && s.status.includes('Expedited Air');
      const lateBadgeHtml = isDelayed ? `<div style="font-size: 0.7rem; color: var(--accent-rose); font-weight: 700; margin-top: 0.15rem;">⚠️ DELAYED</div>` : (isExpedited ? `<div style="font-size: 0.7rem; color: var(--color-green); font-weight: 700; margin-top: 0.15rem;">✈️ EXPEDITED AIR</div>` : '');
      return `
        <tr>
          <td><strong>${s.shipment_code}</strong></td>
          <td>${s.supplier_name}</td>
          <td>${s.product_name}</td>
          <td>${s.quantity} units</td>
          <td style="color: var(--accent-emerald); font-weight: 600;">${rec} units</td>
          <td style="color: var(--accent-rose); font-weight: 600;">${rem} units</td>
          <td>${s.origin} ➔ ${s.destination}</td>
          <td>
            ${formatUserDate(s.expected_delivery_date)}
            ${lateBadgeHtml}
          </td>
          <td>
            <select style="background: rgba(11,15,25,0.8); border: 1px solid var(--border-glow); border-radius: 6px; color: #fff; padding: 0.3rem 0.5rem; font-size: 0.78rem;" onchange="updateShipmentStatus(${s.id}, this.value)">
              ${statusOptions}
            </select>
          </td>
          <td style="display: flex; gap: 0.3rem;">
            <button class="btn btn-outline" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="openShipmentTrackingModal(${s.id}, '${s.shipment_code}', '${s.supplier_name.replace(/'/g, "\\'")}', '${s.product_name.replace(/'/g, "\\'")}', ${s.quantity}, ${rec}, ${rem}, '${s.origin} ➔ ${s.destination}', '${s.expected_delivery_date}', '${s.tracking_number}', '${s.status}')">
              Track
            </button>
            ${rem > 0 ? `
              <button class="btn btn-primary" style="padding: 0.2rem 0.5rem; font-size: 0.75rem; background: #059669; border-color: #10b981;" onclick="openReceiveGoodsModal(${s.id}, '${s.shipment_code}', '${s.product_name.replace(/'/g, "\\'")}', ${s.quantity}, ${rec}, ${rem})">
                Receive
              </button>
            ` : ''}
          </td>
        </tr>
      `;
    }).join('');

    // Suppliers
    const supBody = document.getElementById('tbl-suppliers-body');
    supBody.innerHTML = data.suppliers.map(s => {
      const isDelayed = s.delayed_shipments > 0;
      return `
        <tr>
          <td><strong>${s.supplier_code}</strong></td>
          <td>${s.name}</td>
          <td>${s.country}</td>
          <td>${s.contact_email}</td>
          <td>${s.active_shipments} Active</td>
          <td style="color: ${isDelayed ? 'var(--accent-rose)' : 'var(--text-muted)'}; font-weight: 600;">${s.delayed_shipments} Delayed</td>
          <td>${s.units_in_transit} units</td>
          <td>
            <span class="badge ${isDelayed ? 'badge-red' : 'badge-noimpact'}">${s.delivery_status}</span>
          </td>
          <td style="font-size: 0.78rem; color: var(--text-muted);">${s.on_time_delivery}</td>
        </tr>
      `;
    }).join('');

  } catch (err) {
    console.error('Error loading business data:', err);
  }
}

async function updateDataField(table, id, field, value) {
  try {
    const res = await fetch('/api/data/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ table, id, field, value: parseInt(value) || value })
    });
    const data = await res.json();
    if (!res.ok) {
      alert('Update failed: ' + (data.error || 'Unauthorized field update'));
      return;
    }
    loadAllData();
    initDashboard();
  } catch (err) {
    alert('Update failed: ' + err.message);
  }
}

// Reset Database to Seed State
async function resetDatabase() {
  if (!confirm('Are you sure you want to reset the database to clean master seed state?')) return;
  try {
    const res = await fetch('/api/seed/reset', { method: 'POST' });
    const data = await res.json();
    alert(data.message);
    initDashboard();
    loadAllData();
  } catch (err) {
    alert('Reset failed: ' + err.message);
  }
}

// Order Modal Functions
function openOrderModal() {
  document.getElementById('orderModal').style.display = 'flex';
}

function closeOrderModal() {
  document.getElementById('orderModal').style.display = 'none';
}

async function submitNewOrder() {
  const pId = document.getElementById('modalProductSelect').value;
  const cust = document.getElementById('modalCustomerName').value.trim();
  const qty = document.getElementById('modalOrderQty').value;

  if (!cust || !qty) {
    alert('Please enter customer name and quantity.');
    return;
  }

  try {
    const res = await fetch('/api/data/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: pId, customer_name: cust, quantity: parseInt(qty) })
    });
    const data = await res.json();
    if (data.success) {
      alert(`Customer Order ${data.order_number} created successfully. Re-running disruption assessment will reflect updated demand.`);
      closeOrderModal();
      initDashboard();
      loadAllData();
    }
  } catch (err) {
    alert('Error creating customer order: ' + err.message);
  }
}

// Goods Receiving Modal & Logic
function openReceiveGoodsModal(sId, code, prodName, expected, received, remaining) {
  document.getElementById('modalShipmentId').value = sId;
  document.getElementById('modalShipmentCode').innerText = code;
  document.getElementById('modalProductName').innerText = prodName;
  document.getElementById('modalExpectedQty').innerText = `${expected} units`;
  document.getElementById('modalReceivedQty').innerText = `${received} units`;
  document.getElementById('modalRemainingQty').innerText = `${remaining} units`;
  document.getElementById('modalReceiveQtyInput').value = remaining;
  document.getElementById('receiveGoodsModal').style.display = 'flex';
}

function closeReceiveGoodsModal() {
  document.getElementById('receiveGoodsModal').style.display = 'none';
}

async function submitGoodsReceipt() {
  const sId = document.getElementById('modalShipmentId').value;
  const qtyInput = document.getElementById('modalReceiveQtyInput').value;
  const qty = parseInt(qtyInput);
  const remText = document.getElementById('modalRemainingQty').innerText;
  const remQty = parseInt(remText) || 0;

  if (isNaN(qty) || qty <= 0) {
    alert('Please enter a valid positive quantity to receive.');
    return;
  }

  if (qty > remQty) {
    alert(`Cannot receive ${qty} units. Maximum remaining quantity for this shipment is ${remQty} units.`);
    return;
  }

  try {
    const res = await fetch(`/api/shipments/${sId}/receive`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ received_qty: qty })
    });
    const data = await res.json();
    if (data.success) {
      alert(`Receipt recorded for shipment ${data.shipment_code}!\nReceived Now: ${data.received_qty} units\nStatus: ${data.new_status}\nWarehouse Stock: ${data.updated_stock} units`);
      closeReceiveGoodsModal();

      if (data.recalculated_report) {
        activeDisruptionData = data.recalculated_report;
        renderReportView(data.recalculated_report);
        renderImpactTrace(data.recalculated_report.trace);
      }

      initDashboard();
      loadAllData();
    } else {
      alert('Error: ' + (data.error || 'Failed to record goods receipt'));
    }
  } catch (err) {
    alert('Error submitting goods receipt: ' + err.message);
  }
}

async function updateShipmentStatus(sId, newStatus) {
  try {
    const res = await fetch(`/api/shipments/${sId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    });
    const data = await res.json();
    if (data.success) {
      loadAllData();
      initDashboard();
    } else {
      alert('Failed to update status: ' + (data.error || 'Unknown error'));
    }
  } catch (err) {
    alert('Error updating shipment status: ' + err.message);
  }
}

// Shipment Tracking Timeline Modal Functions
function openShipmentTrackingModal(sId, code, suppName, prodName, expected, rec, rem, route, eta, trk, status) {
  document.getElementById('trackShipmentCode').innerText = code;
  document.getElementById('trackSupplierName').innerText = suppName;
  document.getElementById('trackProductName').innerText = prodName;
  document.getElementById('trackRoute').innerText = route;
  const formattedEta = formatUserDate(eta);
  document.getElementById('trackEta').innerText = formattedEta;
  document.getElementById('trackNumber').innerText = trk;

  const badgeEl = document.getElementById('trackStatusBadge');
  let badgeClass = 'badge-noimpact';
  if (status === 'Delayed') badgeClass = 'badge-red';
  else if (status === 'In Transit' || status === 'Partially Received') badgeClass = 'badge-amber';
  badgeEl.innerHTML = `<span class="badge ${badgeClass}">${status.toUpperCase()}</span>`;

  const stepTransitMeta = document.getElementById('stepTransitMeta');
  const stepEtaMeta = document.getElementById('stepEtaMeta');
  const stepReceivedMeta = document.getElementById('stepReceivedMeta');

  if (status === 'Delayed') {
    stepEtaMeta.innerHTML = `<span class="text-red font-bold">⚠️ DELAY DETECTED</span> — Revised ETA: ${formattedEta}`;
  } else {
    stepEtaMeta.innerText = `On Schedule for Delivery on ${formattedEta}`;
  }

  if (status === 'Received') {
    stepReceivedMeta.innerHTML = `<span class="text-green font-bold">✓ Shipment Received</span> — ${expected} units added to stock`;
  } else if (status === 'Partially Received') {
    stepReceivedMeta.innerHTML = `<span class="text-amber font-bold">Partially Received: ${rec} units</span> | Remaining: ${rem} units`;
  } else {
    stepReceivedMeta.innerText = `Awaiting warehouse arrival & intake`;
  }

  document.getElementById('shipmentTrackingModal').style.display = 'flex';
}

function closeShipmentTrackingModal() {
  document.getElementById('shipmentTrackingModal').style.display = 'none';
}

// Order Fulfillment Modal Functions
function openFulfillOrderModal(oId, orderNum, customer, prodName, ordered, fulfilled, remaining, availStock) {
  document.getElementById('modalFulfillOrderId').value = oId;
  document.getElementById('modalFulfillOrderNumber').innerText = orderNum;
  document.getElementById('modalFulfillCustomer').innerText = customer;
  document.getElementById('modalFulfillProductName').innerText = prodName;
  document.getElementById('modalFulfillOrderedQty').innerText = `${ordered} units`;
  document.getElementById('modalFulfillCurrentFulfilled').innerText = `${fulfilled} units`;
  document.getElementById('modalFulfillRemainingQty').innerText = `${remaining} units`;
  document.getElementById('modalFulfillAvailableStock').innerText = `${availStock} units`;

  const defaultFulfill = Math.min(remaining, availStock);
  document.getElementById('modalFulfillQtyInput').value = defaultFulfill > 0 ? defaultFulfill : remaining;

  document.getElementById('fulfillOrderModal').style.display = 'flex';
}

function closeFulfillOrderModal() {
  document.getElementById('fulfillOrderModal').style.display = 'none';
}

async function submitOrderFulfillment() {
  const oId = document.getElementById('modalFulfillOrderId').value;
  const qtyInput = document.getElementById('modalFulfillQtyInput').value;
  const qty = parseInt(qtyInput);

  if (isNaN(qty) || qty <= 0) {
    alert('Please enter a valid positive fulfillment quantity.');
    return;
  }

  try {
    const res = await fetch(`/api/orders/${oId}/fulfill`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fulfill_qty: qty })
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      alert('Fulfillment error: ' + (data.error || 'Failed to fulfill order'));
      return;
    }

    alert(`Order ${data.order_number} fulfilled by ${data.fulfilled_qty} units!\nStatus: ${data.new_status}\nRemaining Inventory Stock: ${data.updated_stock} units`);
    closeFulfillOrderModal();

    if (data.recalculated_report) {
      activeDisruptionData = data.recalculated_report;
      renderReportView(data.recalculated_report);
      renderImpactTrace(data.recalculated_report.trace);
    }

    initDashboard();
    loadAllData();
  } catch (err) {
    alert('Error submitting order fulfillment: ' + err.message);
  }
}
