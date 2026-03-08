"""
Restores all Layer 8 Governance frontend code that was accidentally deleted.
- dashboard.html: adds governance nav entry + section-governance + explanation modal
- dashboard.js:   adds governance entry in showSection titles, loadGovernance() call,
                  and all governance JS functions at end of file
"""

# ════════════════════════════════════════
#  1. PATCH dashboard.html
# ════════════════════════════════════════
html_path = r'c:\Users\saina\Videos\AIML Hack\templates\dashboard.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# ── 1a. Add Governance nav entry before </nav> if missing ──────────
if 'navGovernance' not in html:
    nav_target = '        </nav>'
    gov_nav = '''            <a class="nav-item" data-section="governance" onclick="showSection('governance')" id="navGovernance">
                <span class="nav-icon"><i data-lucide="activity"></i></span>
                <span class="nav-label">Governance L8</span>
            </a>
        </nav>'''
    html = html.replace(nav_target, gov_nav, 1)
    print('Nav entry added')
else:
    print('Nav entry already present')

# ── 1b. Add section-governance + explanation modal before </main> ──
GOVERNANCE_SECTION = '''
        <!-- ═══════════════ SECTION: GOVERNANCE L8 ═══════════════ -->
        <section class="content-section" id="section-governance">

            <!-- Row 1: Model Health + Inventory -->
            <div style="display:grid;grid-template-columns:1fr 320px;gap:1.25rem;margin-bottom:1.25rem;">
                <div class="card">
                    <div class="card-header">
                        <span class="card-icon" style="background:rgba(99,102,241,0.2);">&#9881;</span>
                        <div>
                            <h3>Model Health &mdash; AUC / KS / Gini / Brier</h3>
                            <p style="color:var(--text-secondary);font-size:0.8rem;">RBI MRM Draft Circular — Aug 2024 metrics</p>
                        </div>
                        <button class="btn btn-outline btn-sm" style="margin-left:auto" onclick="loadGovernance()">&#x21BA; Refresh</button>
                    </div>
                    <div id="govPanel1"><div class="empty-state">Loading&#8230;</div></div>
                </div>
                <div class="card">
                    <h3 class="card-title">&#128194; Model Inventory (RMCB)</h3>
                    <div id="govModelInventory"><div class="empty-state">Loading&#8230;</div></div>
                    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
                        <button class="btn btn-outline btn-sm"
                            onclick="showExplanationModal(STATE.currentApp &amp;&amp; STATE.currentApp.case_id)">
                            &#128221; Right to Explanation
                        </button>
                        <button class="btn btn-outline btn-sm"
                            onclick="fetch('/api/layer8/quarterly-report').then(function(r){return r.json();}).then(function(d){showToast('Q-Report: '+d.quarter);console.log(d);})">
                            &#128196; Q-Report
                        </button>
                    </div>
                </div>
            </div>

            <!-- Row 2: PSI Drift + Override Patterns -->
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem;margin-bottom:1.25rem;">
                <div class="card">
                    <h3 class="card-title">&#127777; PSI Feature Drift &mdash; 25 Features</h3>
                    <div id="govPanel2"><div class="empty-state">Loading&#8230;</div></div>
                </div>
                <div class="card">
                    <h3 class="card-title">&#9878; Decision Override Patterns</h3>
                    <div id="govPanel3"><div class="empty-state">Loading&#8230;</div></div>
                </div>
            </div>

            <!-- Row 3: SMA + Retraining -->
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem;margin-bottom:1.25rem;">
                <div class="card">
                    <h3 class="card-title">&#128680; SMA / NPA Early Warning Dashboard</h3>
                    <div id="govPanel4"><div class="empty-state">Loading&#8230;</div></div>
                </div>
                <div class="card">
                    <h3 class="card-title">&#128260; Retraining Pipeline Status</h3>
                    <div id="govPanel5"><div class="empty-state">Loading&#8230;</div></div>
                </div>
            </div>

            <!-- Row 4: CRILC -->
            <div class="card">
                <h3 class="card-title">&#128203; CRILC Submissions (RBI &mdash; Exposures &ge; &#8377;5 Cr)</h3>
                <div id="govPanel6"><div class="empty-state">Loading&#8230;</div></div>
            </div>

        </section>

        <!-- Modal: DPDP Right-to-Explanation (Sec. 14, DPDP Act 2023) -->
        <div class="modal-overlay" id="modalExplanation" style="display:none;">
            <div class="modal" style="max-width:640px;">
                <div class="modal-header">
                    <h3>&#128221; AI Decision Explanation &mdash; DPDP Act 2023</h3>
                    <span class="close" onclick="document.getElementById('modalExplanation').style.display='none'">&times;</span>
                </div>
                <div class="modal-body">
                    <p style="color:var(--text-secondary);font-size:0.85rem;margin-bottom:1rem;">
                        Case: <strong id="explanationCaseId">&mdash;</strong> &mdash;
                        Sec. 14 Right to Explanation, DPDP Act 2023
                    </p>
                    <div id="explanationBody" style="min-height:200px;"></div>
                </div>
            </div>
        </div>
'''

if 'section-governance' not in html:
    html = html.replace('    </main>', GOVERNANCE_SECTION + '\n    </main>', 1)
    print('Governance section + modal added')
else:
    print('Governance section already present')

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print('dashboard.html saved')


# ════════════════════════════════════════
#  2. PATCH dashboard.js
# ════════════════════════════════════════
js_path = r'c:\Users\saina\Videos\AIML Hack\static\js\dashboard.js'
with open(js_path, 'r', encoding='utf-8') as f:
    js = f.read()

# ── 2a. Add governance to showSection titles ────────────────────
OLD_TITLES_END = "        roles: ['Role Management', 'Configure roles and permissions']\n    };"
NEW_TITLES_END = "        roles: ['Role Management', 'Configure roles and permissions'],\n        governance: ['Governance & Compliance', 'RBI MRM — Model Health, Drift, SMA, CRILC']\n    };"
if 'governance:' not in js:
    if OLD_TITLES_END in js:
        js = js.replace(OLD_TITLES_END, NEW_TITLES_END, 1)
        print('showSection titles updated')
    else:
        print('WARNING: could not find titles map to patch')
else:
    print('Governance already in titles map')

# ── 2b. Add loadGovernance() call in showSection ────────────────
OLD_SHOW = "    if (section === 'cam') loadCAMData();\n}"
NEW_SHOW = "    if (section === 'cam') loadCAMData();\n    if (section === 'governance') loadGovernance();\n}"
if 'loadGovernance()' not in js:
    if OLD_SHOW in js:
        js = js.replace(OLD_SHOW, NEW_SHOW, 1)
        print('loadGovernance() call added to showSection')
    else:
        print('WARNING: could not find showSection body to patch')
else:
    print('loadGovernance() already present')

# ── 2c. Append all governance functions at end ─────────────────
GOV_JS = '''

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
        GREEN:'gov-badge-green', AMBER:'gov-badge-amber', RED:'gov-badge-red',
        PASS:'gov-badge-green', FAIL:'gov-badge-red', GREY:'gov-badge-grey',
        LIVE:'gov-badge-green', SHADOW:'gov-badge-amber', RETIRED:'gov-badge-grey',
        HIGH:'gov-badge-red', MEDIUM:'gov-badge-amber', LOW:'gov-badge-green',
        WATCH:'gov-badge-amber', ALERT:'gov-badge-amber', CRITICAL:'gov-badge-red', NPA:'gov-badge-red'
    };
    const cls = map[status] || 'gov-badge-grey';
    return '<span class="gov-badge ' + cls + '">' + (text || status) + '</span>';
}

function renderGovernancePanel1(m) {
    const el = document.getElementById('govPanel1');
    if (!el || !m) return;
    el.innerHTML = '<div class="gov-metrics-grid">' +
        '<div class="gov-metric-card"><div class="gov-metric-label">AUC-ROC</div><div class="gov-metric-value">' + (m.auc_roc != null ? m.auc_roc : '\\u2014') + '</div><div class="gov-metric-sub">Target \\u2265 0.75 ' + ragBadge(m.auc_status||'GREY', m.auc_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">KS Statistic</div><div class="gov-metric-value">' + (m.ks_statistic != null ? m.ks_statistic : '\\u2014') + '</div><div class="gov-metric-sub">Target \\u2265 0.40 ' + ragBadge(m.ks_status||'GREY', m.ks_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Gini Coefficient</div><div class="gov-metric-value">' + (m.gini_coefficient != null ? m.gini_coefficient : '\\u2014') + '</div><div class="gov-metric-sub">Target \\u2265 0.50 ' + ragBadge(m.auc_status||'GREY', m.auc_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">F1 Score</div><div class="gov-metric-value">' + (m.f1_score != null ? m.f1_score : '\\u2014') + '</div><div class="gov-metric-sub">Prec: ' + (m.precision||'\\u2014') + ' | Rec: ' + (m.recall||'\\u2014') + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Brier Score</div><div class="gov-metric-value">' + (m.brier_score != null ? m.brier_score : '\\u2014') + '</div><div class="gov-metric-sub">\\u2264 0.15 ideal ' + ragBadge(m.brier_status||'GREY', m.brier_status) + '</div></div>' +
        '<div class="gov-metric-card"><div class="gov-metric-label">Sample Size</div><div class="gov-metric-value">' + (m.sample_size != null ? m.sample_size : 0) + '</div><div class="gov-metric-sub">' + (m.period||'\\u2014') + (m.is_demo ? ' ' + ragBadge('AMBER','DEMO') : '') + '</div></div>' +
        '</div>';
}

function renderGovernancePanel2(drift) {
    const el = document.getElementById('govPanel2');
    if (!el) return;
    const features = drift && drift.features ? drift.features : [];
    const ov = drift && drift.overall_status ? drift.overall_status : 'GREY';
    const rows = features.map(function(f) {
        const rc = f.status === 'RED' ? 'psi-row-red' : f.status === 'AMBER' ? 'psi-row-amber' : '';
        return '<tr class="' + rc + '"><td><code>' + f.feature + '</code></td><td><strong>' + f.psi + '</strong></td><td>' +
            ragBadge(f.status, f.status) + '</td><td>' + (f.ref_count != null ? f.ref_count : '\\u2014') +
            '</td><td>' + (f.cur_count != null ? f.cur_count : '\\u2014') + '</td></tr>';
    }).join('');
    el.innerHTML = '<div class="gov-drift-summary">Overall: ' + ragBadge(ov, ov) +
        ' &nbsp;\\uD83D\\uDD34 <strong>' + (drift && drift.red_count != null ? drift.red_count : 0) + '</strong>' +
        ' &nbsp;\\uD83D\\uDFE1 <strong>' + (drift && drift.amber_count != null ? drift.amber_count : 0) + '</strong>' +
        ' &nbsp;\\uD83D\\uDFE2 <strong>' + (drift && drift.green_count != null ? drift.green_count : 0) + '</strong>' +
        (drift && drift.is_demo ? ' ' + ragBadge('AMBER','DEMO') : '') + '</div>' +
        '<div class="gov-table-wrap"><table class="gov-table"><thead><tr><th>Feature</th><th>PSI</th><th>Status</th><th>Ref N</th><th>Cur N</th></tr></thead><tbody>' +
        (rows || '<tr><td colspan="5" class="empty-state">No drift data yet</td></tr>') +
        '</tbody></table></div>';
}

function renderGovernancePanel3(data) {
    const el = document.getElementById('govPanel3');
    if (!el) return;
    const decisions = data && data.decisions ? data.decisions : {};
    const total = data && data.total_decisions ? data.total_decisions : 0;
    const ovr = data && data.override_rate_pct ? data.override_rate_pct : 0;
    const bars = Object.entries(decisions).map(function(entry) {
        const lbl = entry[0], cnt = entry[1];
        const pct = total ? Math.round(cnt / total * 100) : 0;
        const col = lbl === 'REJECT' ? '#ef4444' : lbl.indexOf('CONDITIONAL') >= 0 ? '#f59e0b' : '#10b981';
        return '<div class="gov-bar-row"><span class="gov-bar-label">' + lbl + '</span>' +
            '<div class="gov-bar-track"><div class="gov-bar-fill" style="width:' + pct + '%;background:' + col + '"></div></div>' +
            '<span class="gov-bar-pct">' + cnt + ' (' + pct + '%)</span></div>';
    }).join('');
    const ovrStatus = ovr > 35 ? 'RED' : ovr > 20 ? 'AMBER' : 'GREEN';
    el.innerHTML =
        '<div class="gov-stat-row"><span>Total Decisions</span><strong>' + total + '</strong></div>' +
        '<div class="gov-stat-row"><span>Override Rate</span><strong>' + ovr + '%</strong> ' + ragBadge(ovrStatus, ovrStatus) + '</div>' +
        '<div class="gov-bars">' + (bars || '<div class="empty-state">No decisions yet</div>') + '</div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">\\u26A0 Demo data</div>' : '');
}

function renderGovernancePanel4(data) {
    const el = document.getElementById('govPanel4');
    if (!el) return;
    const c = data && data.sma_counts ? data.sma_counts : {};
    const cards = [
        {lbl:'REGULAR',           cnt: c.REGULAR   != null ? c.REGULAR   : 0, cls:'sma-regular'},
        {lbl:'SMA-0 (1\\u201330 DPD)', cnt: c['SMA-0'] != null ? c['SMA-0'] : 0, cls:'sma-0'},
        {lbl:'SMA-1 (31\\u201360 DPD)', cnt: c['SMA-1'] != null ? c['SMA-1'] : 0, cls:'sma-1'},
        {lbl:'SMA-2 (61\\u201390 DPD)', cnt: c['SMA-2'] != null ? c['SMA-2'] : 0, cls:'sma-2'},
        {lbl:'NPA (>90 DPD)',     cnt: c.NPA       != null ? c.NPA       : 0, cls:'sma-npa'},
    ].map(function(cc) {
        return '<div class="sma-card ' + cc.cls + '"><div class="sma-card-count">' + cc.cnt +
               '</div><div class="sma-card-label">' + cc.lbl + '</div></div>';
    }).join('');
    const alerts = (data && data.early_warnings ? data.early_warnings : []).map(function(w) {
        return '<div class="gov-alert-row"><span class="gov-alert-signal">' + w.signal +
               '</span><span>' + w.description + '</span>' + ragBadge(w.severity, w.severity) + '</div>';
    }).join('');
    el.innerHTML = '<div class="sma-cards-grid">' + cards + '</div>' +
        '<div class="gov-section-label" style="margin-top:10px;">Early Warning Signals</div>' +
        '<div class="gov-alerts">' + (alerts || '<div class="empty-state">No active warnings</div>') + '</div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">\\u26A0 Demo data</div>' : '');
}

function renderGovernancePanel5(data) {
    const el = document.getElementById('govPanel5');
    if (!el) return;
    const history = (data && data.history ? data.history : []).slice(0, 5).map(function(h) {
        const sc = h.status === 'COMPLETED' ? 'gov-badge-green' : h.status === 'INITIATED' ? 'gov-badge-amber' : 'gov-badge-grey';
        const dt = h.created_at ? new Date(h.created_at).toLocaleDateString() : '\\u2014';
        return '<div class="gov-history-row"><span class="gov-history-trigger">' + h.trigger_type +
               '</span><span>' + dt + '</span><span class="gov-badge ' + sc + '">' + h.status + '</span></div>';
    }).join('');
    const nextDue = data && data.next_retrain_due ? new Date(data.next_retrain_due).toLocaleDateString() : '2026-09-01';
    el.innerHTML =
        '<div class="gov-stat-row"><span>Current Model</span><strong>' + (data && data.current_model ? data.current_model : 'XGB_CREDIT_V4.3') + '</strong></div>' +
        '<div class="gov-stat-row"><span>Shadow Mode</span>' + (data && data.shadow_mode_active ? ragBadge('AMBER','ACTIVE') : ragBadge('GREEN','INACTIVE')) + '</div>' +
        '<div class="gov-stat-row"><span>Next Retrain Due</span><strong>' + nextDue + '</strong></div>' +
        '<div class="gov-stat-row"><span>IMV Due</span><strong>2026-09-01</strong></div>' +
        '<div class="gov-section-label" style="margin-top:12px;">Recent Events</div>' +
        '<div class="gov-history">' + (history || '<div class="empty-state">No retraining events yet</div>') + '</div>' +
        '<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">' +
        '<button class="btn btn-outline btn-sm" onclick="triggerRetraining()">\\uD83D\\uDD04 Trigger Retraining</button>' +
        '<button class="btn btn-outline btn-sm" onclick="runIMV()">\\uD83D\\uDCCB Run IMV Check</button></div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">\\u26A0 Demo data</div>' : '');
}

function renderGovernancePanel6(data) {
    const el = document.getElementById('govPanel6');
    if (!el) return;
    const rows = (data && data.submissions ? data.submissions : []).slice(0, 8).map(function(s) {
        const sc = s.submission_status === 'SUBMITTED' ? 'gov-badge-green' : 'gov-badge-amber';
        return '<tr>' +
            '<td><strong>' + (s.case_id||'\\u2014') + '</strong></td>' +
            '<td>' + (s.borrower_name||'\\u2014') + '</td>' +
            '<td>\\u20B9' + (s.outstanding_cr||0) + ' Cr</td>' +
            '<td>' + (s.sma_status||'\\u2014') + '</td>' +
            '<td>' + (s.quarter||'\\u2014') + '</td>' +
            '<td><span class="gov-badge ' + sc + '">' + (s.submission_status||'\\u2014') + '</span></td>' +
            '</tr>';
    }).join('');
    el.innerHTML =
        '<div class="gov-stat-row"><span>Eligible (\\u2265\\u20B95 Cr)</span><strong>' + (data && data.total != null ? data.total : 0) + '</strong></div>' +
        '<div class="gov-stat-row"><span>Submitted</span>' + ragBadge('GREEN', (data && data.submitted != null ? data.submitted : 0) + ' cases') + '</div>' +
        '<div class="gov-stat-row"><span>Pending</span>' + ragBadge(data && data.pending > 0 ? 'AMBER':'GREEN', (data && data.pending != null ? data.pending : 0) + ' cases') + '</div>' +
        '<div class="gov-table-wrap" style="margin-top:12px;">' +
        '<table class="gov-table"><thead><tr><th>Case ID</th><th>Borrower</th><th>Exposure</th><th>SMA</th><th>Quarter</th><th>Status</th></tr></thead>' +
        '<tbody>' + (rows || '<tr><td colspan="6" class="empty-state">No CRILC eligible cases</td></tr>') + '</tbody></table></div>' +
        (data && data.is_demo ? '<div class="gov-demo-note">\\u26A0 Demo data</div>' : '');
}

function renderModelInventoryCard(inv) {
    const el = document.getElementById('govModelInventory');
    if (!el || !inv) return;
    el.innerHTML =
        '<div class="gov-inv-row"><span>Model ID</span><strong>' + (inv.model_id||'\\u2014') + '</strong></div>' +
        '<div class="gov-inv-row"><span>Status</span>' + ragBadge(inv.status, inv.status) + '</div>' +
        '<div class="gov-inv-row"><span>Risk Rating</span>' + ragBadge(inv.model_risk_rating, inv.model_risk_rating) + '</div>' +
        '<div class="gov-inv-row"><span>Model Owner</span>' + (inv.model_owner||'\\u2014') + '</div>' +
        '<div class="gov-inv-row"><span>RMCB Resolution</span>' + (inv.rmcb_resolution_no||'\\u2014') + '</div>' +
        '<div class="gov-inv-row"><span>Last Validated</span>' + (inv.last_validation_date||'\\u2014') + '</div>' +
        '<div class="gov-inv-row"><span>Next Validation</span><strong>' + (inv.next_validation_due||'\\u2014') + '</strong></div>';
}

async function showExplanationModal(caseId) {
    if (!caseId) { showToast('\\u26A0 No case ID available'); return; }
    const modal = document.getElementById('modalExplanation');
    if (!modal) return;
    document.getElementById('explanationCaseId').textContent = caseId;
    document.getElementById('explanationBody').innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    modal.style.display = 'flex';
    try {
        const res = await fetch('/api/applications/' + caseId + '/explanation');
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        const improve = (data.what_can_improve || []).map(function(s) { return '<li>' + s + '</li>'; }).join('');
        const supp = (data.supporting_reasons || []).map(function(s) { return '<li>' + s + '</li>'; }).join('');
        const dc = data.decision && data.decision.indexOf('REJECT') >= 0 ? 'RED' :
                   data.decision && data.decision.indexOf('CONDITIONAL') >= 0 ? 'AMBER' : 'GREEN';
        document.getElementById('explanationBody').innerHTML =
            '<div class="exp-decision">' + ragBadge(dc, data.decision||'\\u2014') + '</div>' +
            '<div class="exp-section"><div class="exp-label">Primary Reason</div><div class="exp-text">' + (data.primary_reason||'\\u2014') + '</div></div>' +
            (supp ? '<div class="exp-section"><div class="exp-label">Supporting Factors</div><ul class="exp-list">' + supp + '</ul></div>' : '') +
            (improve ? '<div class="exp-section"><div class="exp-label">How to Improve Your Application</div><ul class="exp-list imp-list">' + improve + '</ul></div>' : '') +
            '<div class="exp-footer">' +
            '<span>Score: <strong>' + (data.credit_score != null ? data.credit_score : '\\u2014') + '</strong></span>' +
            '<span>Band: <strong>' + (data.risk_band||'\\u2014') + '</strong></span>' +
            '<span>Model: <strong>' + (data.model_version||'v4.3') + '</strong></span>' +
            '</div>';
    } catch(e) {
        document.getElementById('explanationBody').innerHTML =
            '<div style="color:#ef4444">\\u26A0 ' + (e.message || 'Unable to generate explanation') + '</div>';
    }
}

async function triggerRetraining() {
    try {
        const r = await fetch('/api/layer8/trigger-retraining', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({trigger: 'MANUAL', details: {initiated_by: 'dashboard'}})
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        showToast('\\u2705 Retraining event logged \\u2014 ID: ' + d.retrain_id);
        loadGovernance();
    } catch(e) { showToast('\\u274C ' + (e.message || 'Failed')); }
}

async function runIMV() {
    showToast('\\uD83D\\uDD04 Running IMV...');
    try {
        const r = await fetch('/api/layer8/run-imv', {method: 'POST'});
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        showToast('\\u2705 IMV complete \\u2014 ' + d.report.overall_status);
        loadGovernance();
    } catch(e) { showToast('\\u274C ' + (e.message || 'IMV failed')); }
}

function renderGovernancePlaceholder() {
    ['govPanel1','govPanel2','govPanel3','govPanel4','govPanel5','govPanel6'].forEach(function(id) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<div class="empty-state">Loading governance data\\u2026</div>';
    });
}
'''

if 'loadGovernance' not in js:
    js += GOV_JS
    print('Governance JS functions appended')
else:
    print('Governance JS already present')

with open(js_path, 'w', encoding='utf-8') as f:
    f.write(js)
print('dashboard.js saved')

# ════════════════════════════════════════
#  3. VERIFY
# ════════════════════════════════════════
print()
print('=== VERIFICATION ===')
with open(html_path, 'r', encoding='utf-8') as f: html2 = f.read()
with open(js_path,   'r', encoding='utf-8') as f: js2   = f.read()

checks = [
    ('HTML: navGovernance',         'navGovernance' in html2),
    ('HTML: section-governance',    'section-governance' in html2),
    ('HTML: modalExplanation',      'modalExplanation' in html2),
    ('HTML: govPanel1',             'govPanel1' in html2),
    ('HTML: govPanel6',             'govPanel6' in html2),
    ('JS: loadGovernance()',        'loadGovernance' in js2),
    ('JS: ragBadge()',              'ragBadge' in js2),
    ('JS: renderGovernancePanel1()','renderGovernancePanel1' in js2),
    ('JS: triggerRetraining()',     'triggerRetraining' in js2),
    ('JS: showExplanationModal()',  'showExplanationModal' in js2),
    ('JS: governance in titles',    "governance:" in js2),
    ('JS: loadGovernance in show',  "loadGovernance()" in js2),
]
for name, ok in checks:
    print(('OK  ' if ok else 'ERR ') + name)
