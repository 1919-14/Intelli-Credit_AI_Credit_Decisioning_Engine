// ═══════════════════════════════════════════════════════
//  LAYER 8 — GOVERNANCE, MONITORING & COMPLIANCE
// ═══════════════════════════════════════════════════════

async function loadGovernance() {
    try {
        const res = await fetch('/api/layer8/dashboard-data');
        if (!res.ok) throw new Error('API error ' + res.status);
        const data = await res.json();
        renderGovernancePanel1(data.panel1_model_health);
        renderGovernancePanel2(data.panel2_psi_drift);
        renderGovernancePanel3(data.panel3_override_patterns);
        renderGovernancePanel4(data.panel4_sma_dashboard);
        renderGovernancePanel5(data.panel5_retraining);
        renderGovernancePanel6(data.panel6_crilc);
        renderModelInventoryCard(data.model_inventory);
    } catch (e) {
        console.error('Governance load error:', e);
        renderGovernancePlaceholder();
    }
}

function ragBadge(status, text) {
    const map = {
        GREEN: 'gov-badge-green', AMBER: 'gov-badge-amber', RED: 'gov-badge-red',
        PASS: 'gov-badge-green', FAIL: 'gov-badge-red', GREY: 'gov-badge-grey',
        LIVE: 'gov-badge-green', SHADOW: 'gov-badge-amber', RETIRED: 'gov-badge-grey',
        HIGH: 'gov-badge-red', MEDIUM: 'gov-badge-amber', LOW: 'gov-badge-green',
        WATCH: 'gov-badge-amber', ALERT: 'gov-badge-amber', CRITICAL: 'gov-badge-red', NPA: 'gov-badge-red'
    };
    const cls = map[status] || 'gov-badge-grey';
    return '<span class="gov-badge ' + cls + '">' + (text || status) + '</span>';
}

function renderGovernancePanel1(m) {
    const el = document.getElementById('govPanel1');
    if (!el || !m) return;
    el.innerHTML = '<div class="gov-metrics-grid">' +
        '<div class="gov-metric-card"><div class="gov-metric-label">AUC-ROC</div><div class="gov-metric-value">' + (m.auc_roc != null ? m.auc_roc : '—') + '</div><div class="gov-metric-sub">Target ≥ 0.75 ' + ragBadge(m.auc_status || 'GREY', m.auc_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">KS Statistic</div><div class="gov-metric-value">' + (m.ks_statistic != null ? m.ks_statistic : '—') + '</div><div class="gov-metric-sub">Target ≥ 0.40 ' + ragBadge(m.ks_status || 'GREY', m.ks_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Gini Coefficient</div><div class="gov-metric-value">' + (m.gini_coefficient != null ? m.gini_coefficient : '—') + '</div><div class="gov-metric-sub">Target ≥ 0.50 ' + ragBadge(m.auc_status || 'GREY', m.auc_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">F1 Score</div><div class="gov-metric-value">' + (m.f1_score != null ? m.f1_score : '—') + '</div><div class="gov-metric-sub">Prec: ' + (m.precision || '—') + ' | Rec: ' + (m.recall || '—') + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Brier Score</div><div class="gov-metric-value">' + (m.brier_score != null ? m.brier_score : '—') + '</div><div class="gov-metric-sub">Calibration ≤0.15 ' + ragBadge(m.brier_status || 'GREY', m.brier_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Sample Size</div><div class="gov-metric-value">' + (m.sample_size != null ? m.sample_size : 0) + '</div><div class="gov-metric-sub">' + (m.period || '—') + (m.is_demo ? ' ' + ragBadge('AMBER', 'DEMO') : '') + '</div></div>' +
        '</div>';
}

function renderGovernancePanel2(drift) {
    const el = document.getElementById('govPanel2');
    if (!el) return;
    const features = drift && drift.features ? drift.features : [];
    const ov = drift && drift.overall_status ? drift.overall_status : 'GREY';
    const rows = features.map(function (f) {
        const rc = f.status === 'RED' ? 'psi-row-red' : f.status === 'AMBER' ? 'psi-row-amber' : '';
        return '<tr class="' + rc + '"><td><code>' + f.feature + '</code></td><td><strong>' + f.psi + '</strong></td><td>' + ragBadge(f.status, f.status) + '</td><td>' + (f.ref_count != null ? f.ref_count : '—') + '</td><td>' + (f.cur_count != null ? f.cur_count : '—') + '</td></tr>';
    }).join('');
    el.innerHTML = '<div class="gov-drift-summary">Overall: ' + ragBadge(ov, ov) +
        ' &nbsp;🔴 <strong>' + (drift && drift.red_count != null ? drift.red_count : 0) + '</strong>' +
        ' &nbsp;🟡 <strong>' + (drift && drift.amber_count != null ? drift.amber_count : 0) + '</strong>' +
        ' &nbsp;🟢 <strong>' + (drift && drift.green_count != null ? drift.green_count : 0) + '</strong>' +
        (drift && drift.is_demo ? ' ' + ragBadge('AMBER', 'DEMO') : '') + '</div>' +
        '<div class="gov-table-wrap"><table class="gov-table"><thead><tr><th>Feature</th><th>PSI</th><th>Status</th><th>Ref N</th><th>Cur N</th></tr></thead><tbody>' +
        (rows || '<tr><td colspan="5" class="empty-state">No drift data</td></tr>') +
        '</tbody></table></div>';
}

function renderGovernancePanel3(data) {
    const el = document.getElementById('govPanel3');
    if (!el) return;
    const decisions = data && data.decisions ? data.decisions : {};
    const total = data && data.total_decisions ? data.total_decisions : 0;
    const ovr = data && data.override_rate_pct ? data.override_rate_pct : 0;
    const bars = Object.entries(decisions).map(function (entry) {
        const lbl = entry[0], cnt = entry[1];
        const pct = total ? Math.round(cnt / total * 100) : 0;
        const col = lbl === 'REJECT' ? '#ef4444' : lbl.indexOf('CONDITIONAL') >= 0 ? '#f59e0b' : '#10b981';
        return '<div class="gov-bar-row"><span class="gov-bar-label">' + lbl + '</span>' +
            '<div class="gov-bar-track"><div class="gov-bar-fill" style="width:' + pct + '%;background:' + col + '"></div></div>' +
            '<span class="gov-bar-pct">' + cnt + ' (' + pct + '%)</span></div>';
    }).join('');
    const ovrStatus = ovr > 35 ? 'RED' : ovr > 20 ? 'AMBER' : 'GREEN';
    el.innerHTML = '<div class="gov-stat-row"><span>Total Decisions</span><strong>' + total + '</strong></div>' +
        '<div class="gov-stat-row"><span>Override Rate</span><strong>' + ovr + '%</strong> ' + ragBadge(ovrStatus, ovrStatus) + '</div>' +
        '<div class="gov-bars">' + (bars || '<div class="empty-state">No decisions yet</div>') + '</div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">⚠ Demo data</div>' : '');
}

function renderGovernancePanel4(data) {
    const el = document.getElementById('govPanel4');
    if (!el) return;
    const c = data && data.sma_counts ? data.sma_counts : {};
    const cards = [
        { lbl: 'REGULAR', cnt: c.REGULAR != null ? c.REGULAR : 0, cls: 'sma-regular' },
        { lbl: 'SMA-0 (1–30 DPD)', cnt: c['SMA-0'] != null ? c['SMA-0'] : 0, cls: 'sma-0' },
        { lbl: 'SMA-1 (31–60 DPD)', cnt: c['SMA-1'] != null ? c['SMA-1'] : 0, cls: 'sma-1' },
        { lbl: 'SMA-2 (61–90 DPD)', cnt: c['SMA-2'] != null ? c['SMA-2'] : 0, cls: 'sma-2' },
        { lbl: 'NPA (>90 DPD)', cnt: c.NPA != null ? c.NPA : 0, cls: 'sma-npa' },
    ].map(function (cc) {
        return '<div class="sma-card ' + cc.cls + '"><div class="sma-card-count">' + cc.cnt + '</div><div class="sma-card-label">' + cc.lbl + '</div></div>';
    }).join('');
    const alerts = (data && data.early_warnings ? data.early_warnings : []).map(function (w) {
        return '<div class="gov-alert-row"><span class="gov-alert-signal">' + w.signal + '</span><span>' + w.description + '</span>' + ragBadge(w.severity, w.severity) + '</div>';
    }).join('');
    el.innerHTML = '<div class="sma-cards-grid">' + cards + '</div>' +
        '<div class="gov-section-label">Early Warning Signals</div>' +
        '<div class="gov-alerts">' + (alerts || '<div class="empty-state">No active warnings</div>') + '</div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">⚠ Demo data</div>' : '');
}

function renderGovernancePanel5(data) {
    const el = document.getElementById('govPanel5');
    if (!el) return;
    const history = (data && data.history ? data.history : []).slice(0, 5).map(function (h) {
        const sc = h.status === 'COMPLETED' ? 'gov-badge-green' : h.status === 'INITIATED' ? 'gov-badge-amber' : 'gov-badge-grey';
        const dt = h.created_at ? new Date(h.created_at).toLocaleDateString() : '—';
        return '<div class="gov-history-row"><span class="gov-history-trigger">' + h.trigger_type + '</span><span>' + dt + '</span><span class="gov-badge ' + sc + '">' + h.status + '</span></div>';
    }).join('');
    const nextDue = data && data.next_retrain_due ? new Date(data.next_retrain_due).toLocaleDateString() : '2026-09-01';
    el.innerHTML = '<div class="gov-stat-row"><span>Current Model</span><strong>' + (data && data.current_model ? data.current_model : 'XGB_CREDIT_V4.3') + '</strong></div>' +
        '<div class="gov-stat-row"><span>Shadow Mode</span>' + (data && data.shadow_mode_active ? ragBadge('AMBER', 'ACTIVE') : ragBadge('GREEN', 'INACTIVE')) + '</div>' +
        '<div class="gov-stat-row"><span>Next Retrain Due</span><strong>' + nextDue + '</strong></div>' +
        '<div class="gov-stat-row"><span>IMV Due</span><strong>2026-09-01</strong></div>' +
        '<div class="gov-section-label" style="margin-top:12px">Recent Events</div>' +
        '<div class="gov-history">' + (history || '<div class="empty-state">No retraining events</div>') + '</div>' +
        '<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">' +
        '<button class="btn btn-outline btn-sm" onclick="triggerRetraining()">🔄 Trigger Retraining</button>' +
        '<button class="btn btn-outline btn-sm" onclick="runIMV()">📋 Run IMV Check</button></div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">⚠ Demo data</div>' : '');
}

function renderGovernancePanel6(data) {
    const el = document.getElementById('govPanel6');
    if (!el) return;
    const rows = (data && data.submissions ? data.submissions : []).slice(0, 6).map(function (s) {
        const sc = s.submission_status === 'SUBMITTED' ? 'gov-badge-green' : 'gov-badge-amber';
        return '<tr><td><strong>' + (s.case_id || '—') + '</strong></td><td>' + (s.borrower_name || '—') + '</td><td>₹' + (s.outstanding_cr || 0) + ' Cr</td><td>' + (s.sma_status || '—') + '</td><td>' + (s.quarter || '—') + '</td><td><span class="gov-badge ' + sc + '">' + (s.submission_status || '—') + '</span></td></tr>';
    }).join('');
    el.innerHTML = '<div class="gov-stat-row"><span>Eligible (≥₹5Cr)</span><strong>' + (data && data.total != null ? data.total : 0) + '</strong></div>' +
        '<div class="gov-stat-row"><span>Submitted</span>' + ragBadge('GREEN', (data && data.submitted != null ? data.submitted : 0) + ' cases') + '</div>' +
        '<div class="gov-stat-row"><span>Pending</span>' + ragBadge(data && data.pending > 0 ? 'AMBER' : 'GREEN', (data && data.pending != null ? data.pending : 0) + ' cases') + '</div>' +
        '<div class="gov-table-wrap" style="margin-top:12px">' +
        '<table class="gov-table"><thead><tr><th>Case ID</th><th>Borrower</th><th>Exposure</th><th>SMA</th><th>Quarter</th><th>Status</th></tr></thead>' +
        '<tbody>' + (rows || '<tr><td colspan="6" class="empty-state">No eligible cases</td></tr>') + '</tbody></table></div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">⚠ Demo data</div>' : '');
}

function renderModelInventoryCard(inv) {
    const el = document.getElementById('govModelInventory');
    if (!el || !inv) return;
    el.innerHTML =
        '<div class="gov-inv-row"><span>Model ID</span><strong>' + (inv.model_id || '—') + '</strong></div>' +
        '<div class="gov-inv-row"><span>Status</span>' + ragBadge(inv.status, inv.status) + '</div>' +
        '<div class="gov-inv-row"><span>Risk Rating</span>' + ragBadge(inv.model_risk_rating, inv.model_risk_rating) + '</div>' +
        '<div class="gov-inv-row"><span>Model Owner</span>' + (inv.model_owner || '—') + '</div>' +
        '<div class="gov-inv-row"><span>RMCB Resolution</span>' + (inv.rmcb_resolution_no || '—') + '</div>' +
        '<div class="gov-inv-row"><span>Last Validated</span>' + (inv.last_validation_date || '—') + '</div>' +
        '<div class="gov-inv-row"><span>Next Validation</span><strong>' + (inv.next_validation_due || '—') + '</strong></div>';
}

async function showExplanationModal(caseId) {
    if (!caseId) { showToast('⚠ No case ID'); return; }
    const modal = document.getElementById('modalExplanation');
    if (!modal) return;
    document.getElementById('explanationCaseId').textContent = caseId;
    document.getElementById('explanationBody').innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    modal.style.display = 'flex';
    try {
        const res = await fetch('/api/applications/' + caseId + '/explanation');
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        const improve = (data.what_can_improve || []).map(function (s) { return '<li>' + s + '</li>'; }).join('');
        const supp = (data.supporting_reasons || []).map(function (s) { return '<li>' + s + '</li>'; }).join('');
        const dc = data.decision && data.decision.indexOf('REJECT') >= 0 ? 'RED' : data.decision && data.decision.indexOf('CONDITIONAL') >= 0 ? 'AMBER' : 'GREEN';
        document.getElementById('explanationBody').innerHTML =
            '<div class="exp-decision">' + ragBadge(dc, data.decision || '—') + '</div>' +
            '<div class="exp-section"><div class="exp-label">Primary Reason</div><div class="exp-text">' + (data.primary_reason || '—') + '</div></div>' +
            (supp ? '<div class="exp-section"><div class="exp-label">Supporting Factors</div><ul class="exp-list">' + supp + '</ul></div>' : '') +
            (improve ? '<div class="exp-section"><div class="exp-label">How to Improve</div><ul class="exp-list imp-list">' + improve + '</ul></div>' : '') +
            '<div class="exp-footer"><span>Score: <strong>' + (data.credit_score != null ? data.credit_score : '—') + '</strong></span><span>Band: <strong>' + (data.risk_band || '—') + '</strong></span><span>Model: <strong>' + (data.model_version || 'v4.3') + '</strong></span></div>';
    } catch (e) {
        document.getElementById('explanationBody').innerHTML = '<div style="color:#ef4444">⚠ ' + (e.message || 'No explanation available') + '</div>';
    }
}

async function triggerRetraining() {
    try {
        const r = await fetch('/api/layer8/trigger-retraining', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trigger: 'MANUAL', details: { initiated_by: 'dashboard' } })
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        showToast('✅ Retraining event logged — ID: ' + d.retrain_id);
        loadGovernance();
    } catch (e) { showToast('❌ ' + (e.message || 'Failed')); }
}

async function runIMV() {
    showToast('🔄 Running IMV...');
    try {
        const r = await fetch('/api/layer8/run-imv', { method: 'POST' });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        showToast('✅ IMV complete — ' + d.report.overall_status);
        loadGovernance();
    } catch (e) { showToast('❌ ' + (e.message || 'IMV failed')); }
}

function renderGovernancePlaceholder() {
    var ids = ['govPanel1', 'govPanel2', 'govPanel3', 'govPanel4', 'govPanel5', 'govPanel6'];
    ids.forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.innerHTML = '<div class="empty-state">Loading governance data…</div>';
    });
}
