"""Turn Tyler's monthly report-card file into each BU's first TV slide.

Upload the report (.html) into the reports/ folder. The newest month found there is
split by unit (B10 PUP, B20 PEI, B30 TF, B40 HVAC) and written as <BU>/report.html,
a 1920x1080 slide. Imported by build_boards.py.
"""
import glob, os, re

MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
          'september', 'october', 'november', 'december']


def _month_key(text):
    m = re.search(r'(' + '|'.join(MONTHS) + r')\s+(20\d\d)', text, re.I)
    return (int(m.group(2)), MONTHS.index(m.group(1).lower()) + 1) if m else (0, 0)


def latest_report(root):
    files = glob.glob(os.path.join(root, 'reports', '*.htm*'))
    best = None
    for f in files:
        t = open(f, encoding='utf-8', errors='replace').read()
        title = re.search(r'<title>(.*?)</title>', t, re.S)
        key = _month_key(title.group(1) if title else t[:4000])
        if best is None or key > best[0]:
            best = (key, f, t)
    return best


def build(root, boards):
    """Write <folder>/report.html for each board found in the newest report. Returns {folder: label}."""
    found = latest_report(root)
    if not found:
        return {}
    (yr, mo), path, t = found
    css = re.search(r'<style>(.*?)</style>', t, re.S).group(1)
    css = re.sub(r'@media\s*\(prefers-color-scheme:dark\)\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}', '', css)  # keep the light look on every TV
    css = re.sub(r'@media\s*\(max-width:820px\)\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}', '', css)
    sections = re.findall(r'<section class="pg">.*?</section>', t, re.S)
    label = f'{MONTHS[mo-1].title()} {yr}' if yr else 'Report'
    out = {}
    for b in boards:
        sec = next((s for s in sections if re.search(rf'<h2>\s*{b["code"]}\b', s)), None)
        if not sec:
            continue
        sec = re.sub(r'<script.*?</script>', '', sec, flags=re.S | re.I)
        page = f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="color-scheme" content="light">
<title>{b['name']} {label} report card</title><style>{css}
html,body{{margin:0;width:1920px;height:1080px;overflow:hidden;background:#f9f9f7}}
#fit{{position:absolute;left:0;top:0;transform-origin:0 0;width:1480px}}
#fit .pg{{margin:0;border:none;border-radius:0;padding:34px 44px}}
#fit .vd{{max-width:none}}
</style></head><body><div id="fit">{sec}</div>
<script>
const f=document.getElementById('fit');const s=Math.min(1920/f.offsetWidth,1080/f.offsetHeight);
f.style.transform=`scale(${{s}})`;f.style.left=((1920-f.offsetWidth*s)/2)+'px';f.style.top=((1080-f.offsetHeight*s)/2)+'px';
</script></body></html>
'''
        with open(os.path.join(root, b['folder'], 'report.html'), 'w', encoding='utf-8') as fh:
            fh.write(page)
        out[b['folder']] = label
    print(f'report slides from {os.path.basename(path)} ({label}): {sorted(out)}')
    return out
