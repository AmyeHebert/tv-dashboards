"""Use Tyler's monthly BU TV boards as each BU's first TV slide.

Upload Tyler's boards into the reports/ folder, either format:
  - .png / .jpg  : the file name must contain the BU code (B10, B20, B30, B40)
  - .html        : title "TV Board - B10 ...", "TV Board - B20 ...", etc.
For each BU the most recently uploaded board wins. It is copied into the BU folder
and shown as slide 1. Imported by build_boards.py.
"""
import glob, os, re, shutil, subprocess

IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.webp')


def _uploaded_at(root, path):
    """Seconds since epoch of the last commit touching this file (falls back to file time)."""
    try:
        out = subprocess.run(['git', '-C', root, 'log', '-1', '--format=%ct', '--', os.path.relpath(path, root)],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        if out:
            return int(out)
    except Exception:
        pass
    return int(os.path.getmtime(path))


def _code(path):
    name = os.path.basename(path)
    if name.lower().endswith(IMAGE_EXT):
        m = re.search(r'B([1-4]0)(?!\d)', name, re.I)
        return f'B{m.group(1)}' if m else None
    if name.lower().endswith(('.html', '.htm')):
        t = open(path, encoding='utf-8', errors='replace').read(4000)
        title = re.search(r'<title>(.*?)</title>', t, re.S | re.I)
        m = re.search(r'TV Board\s*-\s*(B[1-4]0)\b', title.group(1) if title else '', re.I)
        return m.group(1).upper() if m else None
    return None


def build(root, boards):
    """Write slide 1 for each BU that has a board in reports/. Returns {folder: slide file name}."""
    newest = {}  # code -> (uploaded_at, path)
    for f in glob.glob(os.path.join(root, 'reports', '*')):
        code = _code(f)
        if not code:
            continue
        when = _uploaded_at(root, f)
        if code not in newest or when > newest[code][0]:
            newest[code] = (when, f)
    out = {}
    for b in boards:
        if b['code'] not in newest:
            continue
        src = newest[b['code']][1]
        folder = os.path.join(root, b['folder'])
        for old in ('report.html', 'report.png', 'report.jpg', 'report.jpeg', 'report.webp'):
            if os.path.exists(os.path.join(folder, old)):
                os.remove(os.path.join(folder, old))
        if src.lower().endswith(IMAGE_EXT):
            dest = 'report' + os.path.splitext(src)[1].lower()
            shutil.copyfile(src, os.path.join(folder, dest))
        else:
            dest = 'report.html'
            t = open(src, encoding='utf-8', errors='replace').read()
            t = re.sub(r'<script.*?</script>', '', t, flags=re.S | re.I)
            open(os.path.join(folder, dest), 'w', encoding='utf-8').write(t)
        out[b['folder']] = dest
        print(f"slide 1 for {b['folder']}: {os.path.basename(src)} -> {dest}")
    return out
