css_path = r'c:\Users\saina\Videos\AIML Hack\static\css\style.css'
gov_css = """

/* ═══ LAYER 8: GOVERNANCE DASHBOARD STYLES ═══ */
.gov-badge { display:inline-block; padding:2px 8px; border-radius:12px; font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.04em; }
.gov-badge-green  { background:rgba(16,185,129,0.15); color:#10b981; border:1px solid rgba(16,185,129,0.3); }
.gov-badge-amber  { background:rgba(245,158,11,0.15); color:#f59e0b; border:1px solid rgba(245,158,11,0.3); }
.gov-badge-red    { background:rgba(239,68,68,0.15);  color:#ef4444; border:1px solid rgba(239,68,68,0.3); }
.gov-badge-grey   { background:rgba(107,114,128,0.15);color:#9ca3af; border:1px solid rgba(107,114,128,0.3); }
.gov-metrics-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:0.75rem; }
.gov-metric-card  { background:var(--surface-card); border-radius:10px; padding:1rem; border:1px solid var(--border); text-align:center; }
.gov-metric-label { font-size:0.7rem; text-transform:uppercase; letter-spacing:0.06em; color:var(--text-secondary); margin-bottom:0.4rem; }
.gov-metric-value { font-size:1.6rem; font-weight:800; color:var(--text-primary); margin-bottom:0.2rem; }
.gov-metric-sub   { font-size:0.72rem; color:var(--text-secondary); }
.gov-drift-summary { font-size:0.82rem; margin-bottom:0.75rem; color:var(--text-secondary); }
.gov-table-wrap { overflow-x:auto; }
.gov-table { width:100%; border-collapse:collapse; font-size:0.8rem; }
.gov-table th { padding:8px 10px; background:rgba(99,102,241,0.08); color:var(--text-secondary); text-align:left; font-size:0.72rem; text-transform:uppercase; }
.gov-table td { padding:7px 10px; border-bottom:1px solid var(--border); color:var(--text-primary); }
.gov-table tr:hover td { background:rgba(255,255,255,0.02); }
.psi-row-red td  { background:rgba(239,68,68,0.05); }
.psi-row-amber td { background:rgba(245,158,11,0.05); }
.gov-stat-row { display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px solid var(--border); font-size:0.85rem; }
.gov-stat-row span { color:var(--text-secondary); }
.gov-bars { margin-top:0.75rem; display:flex; flex-direction:column; gap:6px; }
.gov-bar-row { display:flex; align-items:center; gap:0.5rem; font-size:0.8rem; }
.gov-bar-label { width:160px; flex-shrink:0; color:var(--text-secondary); font-size:0.77rem; }
.gov-bar-track { flex:1; height:8px; background:rgba(255,255,255,0.05); border-radius:4px; overflow:hidden; }
.gov-bar-fill  { height:100%; border-radius:4px; transition:width 0.8s ease; }
.gov-bar-pct   { min-width:70px; text-align:right; color:var(--text-secondary); font-size:0.77rem; }
.sma-cards-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:0.5rem; margin-bottom:0.75rem; }
.sma-card       { border-radius:8px; padding:0.6rem 0.5rem; text-align:center; border:1px solid var(--border); }
.sma-card-count { font-size:1.6rem; font-weight:800; }
.sma-card-label { font-size:0.62rem; color:var(--text-secondary); margin-top:2px; }
.sma-regular    { background:rgba(16,185,129,0.08); }
.sma-regular .sma-card-count { color:#10b981; }
.sma-0          { background:rgba(245,158,11,0.08); }
.sma-0 .sma-card-count { color:#f59e0b; }
.sma-1          { background:rgba(245,158,11,0.12); }
.sma-1 .sma-card-count { color:#f59e0b; }
.sma-2          { background:rgba(239,68,68,0.1); }
.sma-2 .sma-card-count { color:#ef4444; }
.sma-npa        { background:rgba(239,68,68,0.18); }
.sma-npa .sma-card-count { color:#ef4444; }
.gov-section-label { font-size:0.72rem; text-transform:uppercase; letter-spacing:0.06em; color:var(--text-secondary); margin-bottom:0.4rem; }
.gov-alerts { display:flex; flex-direction:column; gap:6px; }
.gov-alert-row { display:flex; align-items:center; gap:0.5rem; padding:6px 8px; background:rgba(239,68,68,0.06); border-radius:6px; font-size:0.8rem; }
.gov-alert-signal { font-weight:700; font-size:0.72rem; color:#f59e0b; min-width:130px; }
.gov-history { display:flex; flex-direction:column; gap:6px; }
.gov-history-row { display:flex; align-items:center; justify-content:space-between; padding:5px 8px; background:var(--surface-card); border-radius:6px; font-size:0.8rem; }
.gov-history-trigger { font-weight:600; color:var(--text-secondary); font-size:0.75rem; min-width:120px; }
.gov-inv-row { display:flex; justify-content:space-between; align-items:center; padding:5px 0; border-bottom:1px solid var(--border); font-size:0.82rem; }
.gov-inv-row span { color:var(--text-secondary); }
.gov-demo-note { margin-top:8px; font-size:0.72rem; color:#f59e0b; font-style:italic; }
.exp-decision  { margin-bottom:1rem; }
.exp-section   { margin-bottom:1rem; }
.exp-label     { font-size:0.72rem; text-transform:uppercase; letter-spacing:0.06em; color:var(--text-secondary); margin-bottom:0.25rem; }
.exp-text      { font-size:0.9rem; line-height:1.6; color:var(--text-primary); }
.exp-list      { font-size:0.87rem; line-height:1.7; padding-left:1.2rem; color:var(--text-primary); }
.imp-list li   { color:#10b981; }
.exp-footer    { margin-top:1rem; padding-top:0.75rem; border-top:1px solid var(--border); display:flex; gap:1.5rem; flex-wrap:wrap; font-size:0.8rem; color:var(--text-secondary); }
"""

with open(css_path, 'a', encoding='utf-8') as f:
    f.write(gov_css)
print('CSS done')
