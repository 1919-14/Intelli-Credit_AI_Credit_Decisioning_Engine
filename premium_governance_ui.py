"""
Replaces governance CSS with a premium, polished design system.
Then revamps the section-governance HTML with gradient headers, animated stat cards,
and glassmorphism panels.
"""

# ═══ 1. PREMIUM GOVERNANCE CSS ══════════════════════════════════
css_path = r'c:\Users\saina\Videos\AIML Hack\static\css\style.css'

with open(css_path, 'r', encoding='utf-8') as f:
    css = f.read()

# Remove old governance block if exists
start = css.find('/* ═══ LAYER 8')
if start == -1:
    start = css.find('/* LAYER 8')
if start == -1:
    start = css.find('/* ═════════')

if start != -1:
    css = css[:start]
    print('Old governance CSS removed')
else:
    print('No previous governance CSS found')

PREMIUM_CSS = """

/* ══════════════════════════════════════════════════════════
   LAYER 8 — GOVERNANCE DASHBOARD  (Premium Design System)
   ══════════════════════════════════════════════════════════ */

/* ── RAG Badges ─────────────────────────────────────────── */
.gov-badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 10px; border-radius: 20px;
    font-size: 0.7rem; font-weight: 700; letter-spacing: 0.06em;
    text-transform: uppercase; white-space: nowrap;
    position: relative; overflow: hidden;
}
.gov-badge::before {
    content: ''; position: absolute; inset: 0;
    background: linear-gradient(135deg, rgba(255,255,255,0.15), transparent);
    border-radius: inherit;
}
.gov-badge-green  { background: linear-gradient(135deg,rgba(16,185,129,0.25),rgba(16,185,129,0.1)); color:#34d399; border:1px solid rgba(16,185,129,0.4); box-shadow: 0 0 8px rgba(16,185,129,0.15); }
.gov-badge-amber  { background: linear-gradient(135deg,rgba(245,158,11,0.25),rgba(245,158,11,0.1)); color:#fbbf24; border:1px solid rgba(245,158,11,0.4); box-shadow: 0 0 8px rgba(245,158,11,0.15); }
.gov-badge-red    { background: linear-gradient(135deg,rgba(239,68,68,0.25),rgba(239,68,68,0.1));   color:#f87171; border:1px solid rgba(239,68,68,0.4);  box-shadow: 0 0 8px rgba(239,68,68,0.15); }
.gov-badge-grey   { background: rgba(107,114,128,0.15); color:#9ca3af; border:1px solid rgba(107,114,128,0.3); }

/* ── Governance Section Header ───────────────────────────── */
.gov-section-banner {
    background: linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(139,92,246,0.1) 50%, rgba(16,185,129,0.08) 100%);
    border: 1px solid rgba(99,102,241,0.25);
    border-radius: 16px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.5rem;
    display: flex; align-items: center; justify-content: space-between; gap: 1rem;
    position: relative; overflow: hidden;
}
.gov-section-banner::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(99,102,241,0.6), rgba(16,185,129,0.4), transparent);
}
.gov-banner-title  { font-size: 1.2rem; font-weight: 800; color: var(--text-primary); margin: 0 0 2px; }
.gov-banner-sub    { font-size: 0.78rem; color: var(--text-secondary); }
.gov-banner-badges { display: flex; gap: 6px; flex-wrap: wrap; }

/* ── Metric Cards — Panel 1 ──────────────────────────────── */
.gov-metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.75rem;
}
.gov-metric-card {
    background: linear-gradient(135deg, rgba(99,102,241,0.08) 0%, rgba(30,41,59,0.6) 100%);
    border: 1px solid rgba(99,102,241,0.2);
    border-radius: 14px;
    padding: 1.1rem 0.9rem;
    text-align: center;
    position: relative; overflow: hidden;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    cursor: default;
}
.gov-metric-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(99,102,241,0.15);
    border-color: rgba(99,102,241,0.4);
}
.gov-metric-card::after {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, #6366f1, #8b5cf6, #10b981);
    opacity: 0; transition: opacity 0.2s ease;
}
.gov-metric-card:hover::after { opacity: 1; }
.gov-metric-label {
    font-size: 0.65rem; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--text-secondary); margin-bottom: 0.5rem;
}
.gov-metric-value {
    font-size: 1.75rem; font-weight: 800; line-height: 1;
    background: linear-gradient(135deg, #e0e7ff, #a5b4fc);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; margin-bottom: 0.4rem;
}
.gov-metric-sub {
    font-size: 0.68rem; color: var(--text-secondary);
    display: flex; align-items: center; justify-content: center; gap: 4px;
}

/* ── PSI Drift Table — Panel 2 ───────────────────────────── */
.gov-drift-summary {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    font-size: 0.82rem; color: var(--text-secondary);
    background: rgba(255,255,255,0.03);
    border-radius: 10px; padding: 8px 12px; margin-bottom: 0.75rem;
    border: 1px solid rgba(255,255,255,0.06);
}
.gov-table-wrap { overflow-x: auto; border-radius: 10px; border: 1px solid var(--border); }
.gov-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.gov-table thead { background: linear-gradient(135deg, rgba(99,102,241,0.12), rgba(139,92,246,0.08)); }
.gov-table th {
    padding: 9px 12px; color: var(--text-secondary);
    text-align: left; font-size: 0.68rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.07em; white-space: nowrap;
}
.gov-table td { padding: 8px 12px; color: var(--text-primary); border-bottom: 1px solid rgba(255,255,255,0.04); }
.gov-table tbody tr { transition: background 0.15s ease; }
.gov-table tbody tr:hover td { background: rgba(99,102,241,0.05); }
.gov-table tbody tr:last-child td { border-bottom: none; }
.psi-row-red  td { background: rgba(239,68,68,0.06) !important; }
.psi-row-amber td { background: rgba(245,158,11,0.06) !important; }

/* ── Stat Rows (generic) ─────────────────────────────────── */
.gov-stat-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);
    font-size: 0.85rem;
}
.gov-stat-row:last-child { border-bottom: none; }
.gov-stat-row > span:first-child { color: var(--text-secondary); }
.gov-stat-row > strong { color: var(--text-primary); font-weight: 700; }

/* ── Override Bar Chart — Panel 3 ────────────────────────── */
.gov-bars { display: flex; flex-direction: column; gap: 8px; margin-top: 0.75rem; }
.gov-bar-row { display: flex; align-items: center; gap: 8px; }
.gov-bar-label {
    width: 180px; flex-shrink: 0;
    font-size: 0.75rem; color: var(--text-secondary); font-weight: 500;
}
.gov-bar-track {
    flex: 1; height: 10px; background: rgba(255,255,255,0.06);
    border-radius: 6px; overflow: hidden; position: relative;
}
.gov-bar-fill {
    height: 100%; border-radius: 6px;
    transition: width 1s cubic-bezier(0.4,0,0.2,1);
    position: relative; overflow: hidden;
}
.gov-bar-fill::after {
    content: '';
    position: absolute; inset: 0;
    background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.2) 50%, transparent 100%);
    background-size: 200% 100%; animation: shimmer 2s infinite;
}
.gov-bar-pct { min-width: 72px; text-align: right; font-size: 0.75rem; color: var(--text-secondary); }

/* ── SMA Cards — Panel 4 ─────────────────────────────────── */
.sma-cards-grid {
    display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin-bottom: 1rem;
}
.sma-card {
    border-radius: 12px; padding: 0.75rem 0.5rem; text-align: center;
    border: 1px solid rgba(255,255,255,0.07);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    cursor: default; position: relative; overflow: hidden;
}
.sma-card:hover { transform: translateY(-3px); }
.sma-card-count { font-size: 1.8rem; font-weight: 900; line-height: 1; margin-bottom: 4px; }
.sma-card-label { font-size: 0.6rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); }

.sma-regular { background: linear-gradient(135deg, rgba(16,185,129,0.12), rgba(16,185,129,0.04)); border-color: rgba(16,185,129,0.3); }
.sma-regular .sma-card-count { color: #34d399; }
.sma-0 { background: linear-gradient(135deg, rgba(245,158,11,0.12), rgba(245,158,11,0.04)); border-color: rgba(245,158,11,0.3); }
.sma-0 .sma-card-count { color: #fbbf24; }
.sma-1 { background: linear-gradient(135deg, rgba(245,158,11,0.16), rgba(245,158,11,0.06)); border-color: rgba(245,158,11,0.35); }
.sma-1 .sma-card-count { color: #f59e0b; }
.sma-2 { background: linear-gradient(135deg, rgba(239,68,68,0.14), rgba(239,68,68,0.05)); border-color: rgba(239,68,68,0.3); }
.sma-2 .sma-card-count { color: #f87171; }
.sma-npa { background: linear-gradient(135deg, rgba(239,68,68,0.22), rgba(220,38,38,0.1)); border-color: rgba(239,68,68,0.45); }
.sma-npa .sma-card-count { color: #ef4444; text-shadow: 0 0 12px rgba(239,68,68,0.5); }

.gov-section-label {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--text-secondary); margin-bottom: 6px;
}
.gov-alerts { display: flex; flex-direction: column; gap: 6px; }
.gov-alert-row {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 10px;
    background: linear-gradient(135deg, rgba(239,68,68,0.08), rgba(245,158,11,0.05));
    border-radius: 8px; border: 1px solid rgba(239,68,68,0.18);
    font-size: 0.8rem; transition: background 0.15s ease;
}
.gov-alert-row:hover { background: linear-gradient(135deg, rgba(239,68,68,0.13), rgba(245,158,11,0.08)); }
.gov-alert-signal {
    font-weight: 700; font-size: 0.7rem; color: #fbbf24;
    min-width: 140px; flex-shrink: 0;
}

/* ── Retraining History — Panel 5 ───────────────────────── */
.gov-history { display: flex; flex-direction: column; gap: 6px; }
.gov-history-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 7px 10px;
    background: rgba(255,255,255,0.03);
    border-radius: 8px; border: 1px solid rgba(255,255,255,0.06);
    font-size: 0.8rem; transition: border-color 0.15s ease;
}
.gov-history-row:hover { border-color: rgba(99,102,241,0.3); }
.gov-history-trigger {
    font-weight: 700; font-size: 0.72rem; color: #a5b4fc; min-width: 130px;
}

/* ── Model Inventory ─────────────────────────────────────── */
.gov-inv-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 7px 0; border-bottom: 1px solid rgba(255,255,255,0.05);
    font-size: 0.82rem;
}
.gov-inv-row:last-child { border-bottom: none; }
.gov-inv-row > span:first-child { color: var(--text-secondary); }
.gov-inv-row > strong { color: var(--text-primary); }

/* ── Right-to-Explanation Modal ──────────────────────────── */
.exp-decision { margin-bottom: 1.2rem; }
.exp-section  { margin-bottom: 1rem; }
.exp-label {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--text-secondary); margin-bottom: 5px;
}
.exp-text { font-size: 0.9rem; line-height: 1.7; color: var(--text-primary); }
.exp-list {
    font-size: 0.87rem; line-height: 1.8; padding-left: 1.2rem;
    color: var(--text-primary);
}
.imp-list li { color: #34d399; }
.exp-footer {
    margin-top: 1rem; padding-top: 0.75rem;
    border-top: 1px solid rgba(255,255,255,0.07);
    display: flex; gap: 1.5rem; flex-wrap: wrap;
    font-size: 0.8rem; color: var(--text-secondary);
}

/* ── Demo Note ───────────────────────────────────────────── */
.gov-demo-note {
    margin-top: 8px; font-size: 0.72rem;
    color: #fbbf24; font-style: italic; opacity: 0.8;
}

/* ── Pipeline Step Pills (pp2-pp7) ───────────────────────── */
.pp-step {
    font-size: 0.65rem; font-weight: 700; padding: 2px 8px;
    border-radius: 99px; border: 1px solid rgba(255,255,255,0.1);
    color: #4b5563; background: rgba(255,255,255,0.04);
    transition: all 0.3s ease; letter-spacing: 0.04em;
}
.pp-step.active {
    color: #a78bfa; border-color: rgba(167,139,250,0.5);
    background: rgba(167,139,250,0.15);
    box-shadow: 0 0 8px rgba(167,139,250,0.3);
    animation: pulse-pill 1.5s infinite;
}
.pp-step.done {
    color: #34d399; border-color: rgba(52,211,153,0.4);
    background: rgba(52,211,153,0.1);
}
@keyframes pulse-pill {
    0%, 100% { box-shadow: 0 0 6px rgba(167,139,250,0.3); }
    50%       { box-shadow: 0 0 14px rgba(167,139,250,0.6); }
}

/* ── Governance Card Accent Lines ────────────────────────── */
#section-governance .card {
    border-top: 1px solid rgba(99,102,241,0.15);
    transition: border-color 0.2s ease;
}
#section-governance .card:hover {
    border-top-color: rgba(99,102,241,0.35);
}
#section-governance .card-title {
    font-size: 0.88rem; font-weight: 700;
    color: var(--text-primary);
    padding-bottom: 0.75rem;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    margin-bottom: 0.75rem;
    display: flex; align-items: center; gap: 6px;
}
"""

css += PREMIUM_CSS
with open(css_path, 'w', encoding='utf-8') as f:
    f.write(css)
print('Premium governance CSS written')

# ═══ 2. REVAMP section-governance HTML ══════════════════════════
html_path = r'c:\Users\saina\Videos\AIML Hack\templates\dashboard.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# Replace the plain section-governance with the premium version
import re

NEW_SECTION = """
        <!-- ═══════════════ SECTION: GOVERNANCE L8 ═══════════════ -->
        <section class="content-section" id="section-governance">

            <!-- Banner Header -->
            <div class="gov-section-banner">
                <div>
                    <h2 class="gov-banner-title">&#127959; Governance, Monitoring &amp; Compliance</h2>
                    <p class="gov-banner-sub">RBI MRM Draft Circular (Aug 2024) &middot; DPDP Act 2023 &middot; CRILC Reporting &middot; Basel II</p>
                </div>
                <div class="gov-banner-badges">
                    <span class="gov-badge gov-badge-green">&#10003; Live Monitoring</span>
                    <span class="gov-badge gov-badge-amber">&#128198; Quarterly IMV</span>
                    <span class="gov-badge gov-badge-grey">&#128196; CRILC Compliant</span>
                    <button class="btn btn-outline btn-sm" onclick="loadGovernance()" style="margin-left:8px;">&#x21BA; Refresh All</button>
                </div>
            </div>

            <!-- Row 1: Model Health + Inventory -->
            <div style="display:grid;grid-template-columns:1fr 300px;gap:1.25rem;margin-bottom:1.25rem;">

                <div class="card">
                    <div class="card-header" style="margin-bottom:0.75rem;">
                        <span class="card-icon" style="background:linear-gradient(135deg,rgba(99,102,241,0.3),rgba(139,92,246,0.2));">&#128200;</span>
                        <div>
                            <h3 style="margin:0 0 2px;">Model Performance Metrics</h3>
                            <p style="font-size:0.76rem;color:var(--text-secondary);margin:0;">RBI MRM Circular &sect;4.2 &mdash; AUC, KS, Gini, Brier thresholds</p>
                        </div>
                    </div>
                    <div id="govPanel1"><div class="empty-state" style="padding:2rem;">&#8987; Loading metrics&hellip;</div></div>
                </div>

                <div class="card" style="display:flex;flex-direction:column;">
                    <div class="card-title">&#128194; Model Registry (RMCB)</div>
                    <div id="govModelInventory" style="flex:1;"><div class="empty-state">Loading&hellip;</div></div>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;padding-top:10px;border-top:1px solid rgba(255,255,255,0.06);">
                        <button class="btn btn-outline btn-sm"
                            onclick="showExplanationModal(STATE.currentApp &amp;&amp; STATE.currentApp.case_id)"
                            style="flex:1;font-size:0.72rem;">
                            &#128221; Right to Explanation
                        </button>
                        <button class="btn btn-outline btn-sm"
                            onclick="fetch('/api/layer8/quarterly-report').then(function(r){return r.json();}).then(function(d){showToast('Q-Report generated: '+d.quarter);console.log(d);})"
                            style="flex:1;font-size:0.72rem;">
                            &#128196; Q-Report
                        </button>
                    </div>
                </div>

            </div>

            <!-- Row 2: PSI Drift + Override Patterns -->
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem;margin-bottom:1.25rem;">
                <div class="card">
                    <div class="card-title">&#127777; PSI Feature Drift &mdash; 25 Credit Features</div>
                    <div id="govPanel2"><div class="empty-state">Loading&hellip;</div></div>
                </div>
                <div class="card">
                    <div class="card-title">&#9878;&#65039; Decision &amp; Override Patterns</div>
                    <div id="govPanel3"><div class="empty-state">Loading&hellip;</div></div>
                </div>
            </div>

            <!-- Row 3: SMA Dashboard + Retraining -->
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem;margin-bottom:1.25rem;">
                <div class="card">
                    <div class="card-title">&#128680; SMA / NPA Early Warning Dashboard</div>
                    <div id="govPanel4"><div class="empty-state">Loading&hellip;</div></div>
                </div>
                <div class="card">
                    <div class="card-title">&#128260; Model Retraining Pipeline</div>
                    <div id="govPanel5"><div class="empty-state">Loading&hellip;</div></div>
                </div>
            </div>

            <!-- Row 4: CRILC Full-width -->
            <div class="card">
                <div class="card-title">&#128203; CRILC Submissions &mdash; RBI Mandated (Exposures &ge; &#8377;5 Cr)</div>
                <div id="govPanel6"><div class="empty-state">Loading&hellip;</div></div>
            </div>

        </section>

        <!-- Modal: DPDP Right-to-Explanation (Sec. 14, DPDP Act 2023) -->
        <div class="modal-overlay" id="modalExplanation" style="display:none;">
            <div class="modal" style="max-width:640px;border-top:3px solid #6366f1;">
                <div class="modal-header">
                    <div>
                        <h3 style="margin:0 0 2px;">&#128221; AI Decision Explanation</h3>
                        <p style="font-size:0.75rem;color:var(--text-secondary);margin:0;">Sec. 14 &mdash; DPDP Act 2023 &middot; Right to Explanation</p>
                    </div>
                    <span class="close" onclick="document.getElementById('modalExplanation').style.display='none'">&times;</span>
                </div>
                <div class="modal-body">
                    <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:rgba(99,102,241,0.08);border-radius:8px;border:1px solid rgba(99,102,241,0.2);margin-bottom:1rem;">
                        <span style="font-size:0.75rem;color:var(--text-secondary);">Case ID:</span>
                        <strong id="explanationCaseId" style="color:#a5b4fc;">&mdash;</strong>
                    </div>
                    <div id="explanationBody" style="min-height:200px;"></div>
                </div>
            </div>
        </div>
"""

# Remove old section-governance and modal
pattern = r'<!-- ═══════════════ SECTION: GOVERNANCE L8 ═══════════════ -->.*?(?=\n    </main>|\n        <!-- Modal: DPDP)' 
html_clean = re.sub(pattern, '', html, flags=re.DOTALL)

# Remove old explanation modal too
pattern2 = r'<!-- Modal: DPDP Right-to-Explanation.*?(?=\n    </main>)'
html_clean = re.sub(pattern2, '', html_clean, flags=re.DOTALL)

# Insert new section before </main>
html_clean = html_clean.replace('    </main>', NEW_SECTION + '\n    </main>', 1)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_clean)
print('Premium governance HTML written')

# ═══ 3. VERIFY ══════════════════════════════════════════════════
with open(html_path, 'r', encoding='utf-8') as f: h = f.read()
with open(css_path,  'r', encoding='utf-8') as f: c = f.read()
print('section-governance:', 'OK' if 'section-governance' in h else 'ERR')
print('govPanel1:', 'OK' if 'govPanel1' in h else 'ERR')
print('gov-section-banner:', 'OK' if 'gov-section-banner' in h else 'ERR')
print('modalExplanation:', 'OK' if 'modalExplanation' in h else 'ERR')
print('gov-metric-card CSS:', 'OK' if 'gov-metric-card' in c else 'ERR')
print('sma-npa CSS:', 'OK' if 'sma-npa' in c else 'ERR')
print('DONE')
