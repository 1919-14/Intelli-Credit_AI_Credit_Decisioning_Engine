css_path = r'c:\Users\saina\Videos\AIML Hack\static\css\style.css'
with open(css_path, 'r', encoding='utf-8') as f:
    css = f.read()

markers = [
    '\n/* ══════════════════════════════════════════════════════════\n   LAYER 8',
    '\n/* ═══ LAYER 8',
    '\n/* LAYER 8',
]
idx = -1
for m in markers:
    idx = css.find(m)
    if idx != -1:
        break

if idx != -1:
    css = css[:idx]
    with open(css_path, 'w', encoding='utf-8') as f:
        f.write(css)
    print('Reverted. CSS is now', len(css), 'chars')
else:
    print('Nothing to revert — governance CSS marker not found')
