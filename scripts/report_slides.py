"""Use Tyler's monthly BU TV boards as each BU's first TV slide.

Upload Tyler's TV board files (.html, title "TV Board - B10 ...", "TV Board - B20 ...", etc.)
into the reports/ folder. For each BU code the newest month found there is copied to
<BU>/report.html and shown as slide 1. Imported by build_boards.py.
"""
import glob, os, re

MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
          'september', 'october', 'november', 'december']


def _month_key(text):
    m = re.search(r'(' + '|'.join(MONTHS) + r')\s+(20\d\d)', text, re.I)
    return (int(m.group(2)), MONTHS.index(m.group(1).lower()) + 1) if m else (0, 0)


def build(root, boards):
    """Write <folder>/report.html for each BU with a TV board in reports/. Returns {folder: 'Month YYYY'}."""
    newest = {}  # BU code -> (month key, filename, html)
    for f in glob.glob(os.path.join(root, 'reports', '*.htm*')):
        t = open(f, encoding='utf-8', errors='replace').read()
        title = re.search(r'<title>(.*?)</title>', t, re.S | re.I)
        m = re.search(r'TV Board\s*-\s*(B\d0)\b', title.group(1) if title else '', re.I)
        if not m:
            continue  # not a TV board (e.g. report cards) - ignored
        code = m.group(1).upper()
        body = t.split('</style>', 1)[-1]
        key = _month_key(body)  # the board's "October 2026" heading
        if code not in newest or key > newest[code][0]:
            newest[code] = (key, os.path.basename(f), t)
    out = {}
    for b in boards:
        if b['code'] not in newest:
            continue
        (yr, mo), name, t = newest[b['code']]
        t = re.sub(r'<script.*?</script>', '', t, flags=re.S | re.I)
        with open(os.path.join(root, b['folder'], 'report.html'), 'w', encoding='utf-8') as fh:
            fh.write(t)
        out[b['folder']] = f'{MONTHS[mo-1].title()} {yr}' if yr else name
        print(f"slide 1 for {b['folder']}: {name} ({out[b['folder']]})")
    return out
