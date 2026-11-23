#!/usr/bin/env python3
"""Rebuild the golf-themed BU TV boards from live Pipedrive data.

Runs in GitHub Actions (see .github/workflows/refresh-boards.yml) on a schedule.
Each TV keeps its usual address, e.g. .../TF/tv.html; the page reloads itself
every 30 minutes and picks up whatever this script last published.

Local test without Pipedrive:  python scripts/build_boards.py --from-dir DIR
  (DIR holds open.json, won.json, lost.json in Pipedrive API v2 format)
Live:  PIPEDRIVE_API_TOKEN=... python scripts/build_boards.py
"""
import argparse, collections, datetime as dt, html, json, os, sys, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = ZoneInfo('America/Chicago')
PIPELINE = 14  # All Sales Pipeline

# Pipedrive custom field keys
DEPT = '0b130cea2bf6aa8cbcafd336242b1284833a1ba3'   # Procore Department
PN = '84bc2b081a456eea0fc2f3677f7076ff5b7c86b7'     # Project Number
BID = '9f24c174ab4a88fba242a5dba0d167ce12a4e45d'    # Bid Due Date
DEPT_SHORT = {357: 'TF', 360: 'PEI', 359: 'PUP', 358: 'HVAC', 361: 'Parts'}

# ---- Owners: Pipedrive user id -> name shown on the boards ----
NAME = {21822426: 'Troy Tanner', 24235023: 'Brett Shannon', 22740420: 'Cody Robinson', 21905905: 'Cody Robinson',
        24868799: 'Kyle Rubeck', 23915891: 'Taylor', 24836712: 'Davey', 24398395: 'Chris', 25453438: 'Gustavo',
        26058900: 'Brian', 23393941: 'Aaron', 23362723: 'KJ', 23399606: 'Hunter', 24182355: 'Bob',
        27224636: 'Megan'}
UNCONFIRMED = {'KJ', 'Hunter', 'Bob'}          # shown with *
FORMER = {'Troy Tanner', 'Hunter', 'Bob'}      # shown with Former tag

# ---- Boards to build ----
BOARDS = [
    dict(folder='TF', file='TF_Leaderboard_TV.html', code='B30', dept=357, short='TF', name='Thermal Fluid',
         team=['Davey', 'Taylor']),
    dict(folder='PEI', file='PEI_Leaderboard_TV.html', code='B20', dept=360, short='PEI', name='PEI',
         team=['Chris', 'Brian', 'Gustavo']),
    dict(folder='PUP', file='PUP_Leaderboard_TV.html', code='B10', dept=359, short='PUP', name='PUP',
         team=['Megan', 'KJ']),
    dict(folder='HVAC', file='HVAC_Leaderboard_TV.html', code='B40', dept=358, short='HVAC', name='HVAC',
         team=['Aaron']),
]

# Stage id, name, short label, Pipedrive stage %
STAGES = [(94, 'Potential Opportunity', 'Potential Opportunity', 5), (95, 'Qualified Project', 'Qualified Project', 10),
          (96, 'Pre-Engineering/Design', 'Pre-Eng / Design', 15), (97, 'Estimating', 'Estimating', 20),
          (103, 'Proposal Ready', 'Proposal Ready', 25), (98, 'Proposal Sent', 'Proposal Sent', 35),
          (99, 'Verbal Award', 'Verbal Award', 90), (100, 'Won - Handoff to PM', 'Won', 100)]
STAGE_NAME = {s: n for s, n, _, _ in STAGES}
PRE_PROPOSAL = {94, 95, 96, 97, 103}
PROPOSAL_SENT = 98


# ------------------------------------------------------------------ data
def fetch(token, status, fields, updated_since=None):
    out, cursor = [], None
    while True:
        q = {'pipeline_id': PIPELINE, 'status': status, 'limit': 500, 'custom_fields': ','.join(fields)}
        if updated_since: q['updated_since'] = updated_since
        if cursor: q['cursor'] = cursor
        req = urllib.request.Request('https://api.pipedrive.com/api/v2/deals?' + urllib.parse.urlencode(q),
                                     headers={'x-api-token': token, 'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        if not d.get('success'):
            raise SystemExit(f'Pipedrive error: {d}')
        out += d.get('data') or []
        cursor = (d.get('additional_data') or {}).get('next_cursor')
        if not cursor: return out


def load(args, year):
    if args.from_dir:
        r = lambda f: json.load(open(os.path.join(args.from_dir, f)))['data']
        return r('open.json'), r('won.json'), r('lost.json')
    token = os.environ.get('PIPEDRIVE_API_TOKEN')
    if not token: raise SystemExit('PIPEDRIVE_API_TOKEN is not set')
    since = f'{year}-01-01T00:00:00Z'
    return (fetch(token, 'open', [DEPT, PN, BID]), fetch(token, 'won', [DEPT, PN], since),
            fetch(token, 'lost', [DEPT, PN], since))


# ------------------------------------------------------------------ formatting
e = html.escape
nm = lambda o: NAME.get(o, f'User {o}')
cf = lambda x, k: (x.get('custom_fields') or {}).get(k)
dshort = lambda x: DEPT_SHORT.get(cf(x, DEPT), '—')
def mdy(s): y, m, d = s.split('-'); return f'{int(m)}/{int(d)}/{y[2:]}'
def md(s): y, m, d = s.split('-'); return f'{int(m)}/{int(d)}'
def money(v): return f'${v:,.0f}'
def K(v):
    if not v: return None
    return f'${v/1e6:.2f}M' if v >= 1e6 else f'${v/1e3:.0f}K'
def M(v): return f'${v/1e6:.2f}M' if v >= 1e6 else f'${v/1e3:.0f}K'
def pct(a, b): return f'{round(100*a/b)}%' if b else '—'
def trunc(s, n): return s if len(s) <= n else s[:n-1].rstrip() + '…'
def pnum(x): p = cf(x, PN); return str(int(p)) if p else '—'
def who(n): return e(n) + ('*' if n in UNCONFIRMED else '')
def tag(n):
    s = e(n)
    if n in UNCONFIRMED: s += '<sup>*</sup>'
    if n in FORMER: s += "<span class='fmr'>Former</span>"
    return s

FLAG = ("<svg class='flag' viewBox='0 0 20 28'><line x1='3' y1='1' x2='3' y2='27' stroke='currentColor' stroke-width='2'/>"
        "<path d='M4 2 L18 7 L4 12 Z' fill='#d9b44a'/></svg>")
BIGFLAG = ('<svg class="flagbig" viewBox="0 0 20 28"><line x1="3" y1="1" x2="3" y2="27" stroke="currentColor" stroke-width="2"/>'
           '<path d="M4 2 L18 7 L4 12 Z" fill="#d9b44a"/></svg>')

EXTRA_CSS = '''.pill.blu{background:#2f5d8a}
.p1 .card{padding:10px 22px 12px} .p1 .pname{font-size:42px} .p1 .stats div{padding:10px 10px} .p1 .sv{font-size:48px}
.lb .pl{white-space:nowrap}
.teegrid{display:grid;grid-template-columns:repeat(3,1fr)} .teegrid .tee{grid-template-columns:96px 1fr 104px;border-right:1px solid var(--line);padding:10px 16px} .teegrid .tee:nth-child(3n){border-right:0}
.teegrid .td b{font-size:34px} .teegrid .tp{font-size:20px} .teegrid .tp span{font-size:16px} .teegrid .tv{font-size:30px}
.p3{display:grid;grid-template-columns:1fr 1fr;gap:0} .p3 table:first-child{border-right:3px solid var(--ink)}
.gr.g3 td{font-size:19px;padding:7px 12px} .gr.g3 th{font-size:15px;white-space:nowrap}
'''

SCRIPT = '''<script>
/* SETTINGS: FIN_SRC = the financial board image in this folder ('' to skip). SECONDS = per page:
   financial, leaderboard, pipeline, then each proposals page. This file is rebuilt automatically from Pipedrive. */
const FIN_SRC='board.png';
const SECONDS=[60,60,60,60,60,60]; /* one per page; any page without a number gets 60 */
const fin=document.getElementById('p0');
if(FIN_SRC){fin.innerHTML=/\\.(png|jpe?g|webp)$/i.test(FIN_SRC)?`<img src="${FIN_SRC}" alt="">`:`<iframe src="${FIN_SRC}" scrolling="no"></iframe>`}
else{fin.remove();document.getElementById('p1').classList.add('on');document.querySelectorAll('.dots span:first-child').forEach(x=>x.remove())}
const P=[...document.querySelectorAll('.page')];let i=0;
function sec(){return (FIN_SRC?SECONDS:SECONDS.slice(1))[i]||60}
function show(n){P[i].classList.remove('on');i=(n+P.length)%P.length;P[i].classList.add('on')}
let t;function tick(){clearTimeout(t);t=setTimeout(()=>{show(i+1);tick()},sec()*1000)}tick();
addEventListener('keydown',ev=>{if(ev.key==='ArrowRight'||ev.key===' '){show(i+1)}if(ev.key==='ArrowLeft'){show(i-1)}tick()});
const q=new URLSearchParams(location.search).get('page');if(q)show(+q-1);
function fit(){const s=Math.min(innerWidth/1920,innerHeight/1080),st=document.getElementById('stage');st.style.transform=`scale(${s})`;st.style.left=((innerWidth-1920*s)/2)+'px';st.style.top=((innerHeight-1080*s)/2)+'px'}
addEventListener('resize',fit);fit();
</script></body></html>
'''


def window(today):
    """Bids window: today through Friday. On a weekend, the coming Mon-Fri."""
    if today.weekday() >= 5:
        start = today + dt.timedelta(days=7 - today.weekday())
    else:
        start = today
    end = start + dt.timedelta(days=4 - start.weekday())
    return start, end


# ------------------------------------------------------------------ render one board
def render(b, open_deals, won, lost, today):
    year = str(today.year)
    tiso = today.isoformat()
    ws, we = window(today)
    wsi, wei = ws.isoformat(), we.isoformat()
    wk = f"{ws.strftime('%b')} {ws.day} – {we.day}" if ws.month == we.month else f"{ws.strftime('%b')} {ws.day} – {we.strftime('%b')} {we.day}"
    asof = f'Thru {today.month}/{today.day}/{year[2:]} · Pipedrive'
    w26 = [x for x in won if (x.get('won_time') or '')[:4] == year]
    l26 = [x for x in lost if (x.get('lost_time') or '')[:4] == year and (x.get('lost_reason') or '') != 'Test Record']
    o = [x for x in open_deals if cf(x, DEPT) == b['dept']]

    st = []
    for s, n, sh, p in STAGES:
        xs = [x for x in o if x['stage_id'] == s]; v = sum(x['value'] or 0 for x in xs)
        st.append(dict(n=n, sh=sh, p=p, c=len(xs), v=v, f=None if s == 100 else v * p / 100))
    open_n = sum(r['c'] for r in st); open_v = sum(r['v'] for r in st); fc = sum(r['f'] or 0 for r in st)

    props = sorted([x for x in o if x['stage_id'] == PROPOSAL_SENT], key=lambda x: (cf(x, BID) or '9999', x['title']))
    prop_v = sum(x['value'] or 0 for x in props)

    bids = []
    for x in o:
        d = cf(x, BID)
        if not d: continue
        if wsi <= d <= wei and x['stage_id'] in PRE_PROPOSAL | {PROPOSAL_SENT}:
            bids.append((d, 'sent' if x['stage_id'] == PROPOSAL_SENT else 'due', x))
        elif d < tiso and x['stage_id'] in PRE_PROPOSAL:
            bids.append((d, 'past', x))
    bids.sort(key=lambda t: (t[0], t[2]['title']))
    n_past = sum(1 for t in bids if t[1] == 'past'); n_week = len(bids) - n_past

    agg = collections.defaultdict(lambda: [0, 0.0, collections.Counter()])
    for x in w26:
        a = agg[nm(x['owner_id'])]; a[0] += 1; a[1] += x['value'] or 0; a[2][dshort(x)] += x['value'] or 0
    sold = sorted(([k, v[0], v[1], v[2].most_common(1)[0][0]] for k, v in agg.items()), key=lambda t: -t[2])

    W = collections.defaultdict(lambda: dict(w=0, l=0, wv=0.0, lv=0.0, pc=0, pv=0.0))
    for x in w26:
        if cf(x, DEPT) == b['dept']: r = W[nm(x['owner_id'])]; r['w'] += 1; r['wv'] += x['value'] or 0
    for x in l26:
        if cf(x, DEPT) == b['dept']: r = W[nm(x['owner_id'])]; r['l'] += 1; r['lv'] += x['value'] or 0
    for x in props: r = W[nm(x['owner_id'])]; r['pc'] += 1; r['pv'] += x['value'] or 0
    tw = sum(r['w'] for r in W.values()); tl = sum(r['l'] for r in W.values())
    twv = sum(r['wv'] for r in W.values()); tlv = sum(r['lv'] for r in W.values())

    name, code, short = b['name'], b['code'], b['short']
    def hdr(sub, title):
        return (f'<div class="hdr"><div class="l">{BIGFLAG}<div><div class="sub">{code} · {sub}</div><h1>{title}</h1></div></div>\n'
                f'<div class="r"><b>Bids {wk}</b><br>{asof}</div></div>')
    PER_PAGE = 36  # 18 rows per column at full TV size; more proposals roll onto extra pages
    n_pp = max(1, -(-len(props) // PER_PAGE))
    total_pages = 3 + n_pp  # financial board + leaderboard + pipeline + proposal pages
    def dots(on): return '<span class="dots">' + ''.join('<span class="on"></span>' if k == on else '<span></span>' for k in range(total_pages)) + '</span>'

    # page 1 – leaderboard
    rows = ''.join(f"<tr class='{'me' if bu == short else ''}'><td class='pos'>{i}</td><td class='pl'>{tag(k)}</td><td class='bu'>{bu}</td>"
                   f"<td class='c'>{c}</td><td class='r big'>{money(v)}</td></tr>" for i, (k, c, v, bu) in enumerate(sold[:13], 1))
    cards = ''
    for n in b['team']:
        r = W[n]
        cards += (f"<div class='card'><div class='pname'>{FLAG}{e(n)}</div>\n<div class='stats'>"
                  f"<div><span class='sv'>{r['pc']}</span><span class='sl'>Proposals out</span><span class='ss'>{K(r['pv']) or '$0'}</span></div>\n"
                  f"<div><span class='sv'>{r['w']}<i>/{r['w']+r['l']}</i></span><span class='sl'>Won / closed</span><span class='ss'>{K(r['wv']) or '$0'} won</span></div>\n"
                  f"<div><span class='sv'>{pct(r['w'], r['w']+r['l'])}</span><span class='sl'>Win % · #</span></div>\n"
                  f"<div><span class='sv'>{pct(r['wv'], r['wv']+r['lv'])}</span><span class='sl'>Win % · $</span></div></div></div>")
    ow = sorted([k for k in W if k not in b['team'] and W[k]['w']], key=lambda k: -W[k]['wv'])
    oth = ''
    if ow:
        names = ', '.join(e(k) + (' (Former)' if k in FORMER else '') + ('*' if k in UNCONFIRMED else '') for k in ow)
        oth = (f"<div class='oth'>Also won {e(name)} work YTD: {names} · {sum(W[k]['w'] for k in ow)} won / "
               f"{sum(W[k]['w']+W[k]['l'] for k in ow)} closed · {K(sum(W[k]['wv'] for k in ow))} won</div>")
    p1 = f'''<div class="page" id="p1">
{hdr(f'{year} Sales Season', f'{name} Leaderboard')}
<div class="p1">
<div class="panel"><div class="ptitle">Sold YTD · All BUs <small>Ranked by $ won</small></div>
<table class="lb"><thead><tr><th style="text-align:center">Pos</th><th>Player</th><th>BU</th><th class="c">Wins</th><th class="r">Sold YTD</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="right">
<div class="team"><div><span>Open pipeline</span><b>{M(open_v)}</b><em>{open_n} deals</em></div><div><span>Forecast</span><b>{M(fc)}</b><em>Stage % × value</em></div><div><span>Win % · #</span><b>{pct(tw, tw+tl)}</b><em>{tw} of {tw+tl} closed</em></div><div><span>Win % · $</span><b>{pct(twv, twv+tlv)}</b><em>{M(twv)} of {M(twv+tlv)}</em></div></div>
<div class="panel"><div class="ptitle">{e(name)} Team Scorecard <small>{year} YTD</small></div>{cards}{oth}</div>
</div></div>
<div class="foot"><span><sup style="color:#ff8a7a">*</sup> Name not confirmed in Pipedrive · Former = no longer with ARMI · BU = Procore Department · Win % on deals closed in {year}</span>{dots(1)}</div>
</div>'''

    # page 2 – stages + bids
    z = lambda v: v if v else '<span class=z>–</span>'
    th = ''.join(f'<th><b>{i}</b><em>Par {p}%</em><span>{sh}</span></th>' for i, (s, n, sh, p) in enumerate(STAGES, 1))
    r1 = ''.join(f"<td>{z(r['c'])}</td>" for r in st)
    r2 = ''.join(f"<td>{z(K(r['v']))}</td>" for r in st)
    r3 = ''.join("<td><span class=z>n/a</span></td>" if r['f'] is None else f"<td>{z(K(r['f']) if r['f'] >= 500 else None)}</td>" for r in st)
    pill = {'past': ('red', 'Past due'), 'due': ('grn', 'Due'), 'sent': ('blu', 'Sent')}
    shown = bids
    more = ''
    if len(bids) > 15:  # keep this week's bids, then the most recent past-due ones
        week = [t for t in bids if t[1] != 'past']; past = [t for t in bids if t[1] == 'past']
        keep = week[:15] + past[-max(0, 15 - len(week)):] if len(week) < 15 else week[:15]
        shown = sorted(keep, key=lambda t: (t[0], t[2]['title']))
        more = f' · showing {len(shown)} of {len(bids)}'
    tees = ''.join(f"<div class='tee'><div class='td'><b>{md(d)}</b><span class='pill {pill[k][0]}'>{pill[k][1]}</span></div>"
                   f"<div class='tp'>{e(trunc(x['title'], 46))}<span>{who(nm(x['owner_id']))} · {STAGE_NAME[x['stage_id']]} · #{pnum(x)}</span></div>"
                   f"<div class='tv'>{K(x['value']) or '$0'}</div></div>" for d, k, x in shown)
    if not tees: tees = "<div class='none'>No bids due this week and nothing past due.</div>"
    p2 = f'''<div class="page" id="p2">
{hdr('The Course', f'{name} Pipeline')}
<div class="panel" style="margin-top:16px"><table class="sc"><thead><tr><th class="hl">STAGE</th>{th}<th class="tot">TOTAL</th></tr></thead><tbody><tr class=''><td class='rl'>Deals</td>{r1}<td class='tot'>{open_n}</td></tr><tr class=''><td class='rl'>Value</td>{r2}<td class='tot'>{M(open_v)}</td></tr><tr class='fc'><td class='rl'>Forecast</td>{r3}<td class='tot'>{M(fc)}</td></tr></tbody></table></div>
<div class="panel" style="margin-top:20px"><div class="ptitle">Tee Times · Bids Due <small>{ws.strftime('%a')} {md(wsi)} – {we.strftime('%a')} {md(wei)} + past due, not yet proposed · {n_week} this week · {n_past} past due{more}</small></div><div class="teegrid">{tees}</div></div>
<div class="foot"><span>Par = Pipedrive stage % · Forecast = value × par · Potential Opportunity through Verbal Award · Past due = bid date passed, deal not yet in Proposal Sent</span>{dots(2)}</div>
</div>'''

    # page 3+ – proposals, two columns, 36 per page, extra pages as needed
    def prow(x):
        d = cf(x, BID); ec = x.get('expected_close_date')
        red = 'redt' if (d and ec and ec < d) else ''
        return (f"<tr><td>{mdy(d) if d else '—'}</td><td class='pj'>{e(trunc(x['title'], 36))}</td><td class='dim'>{pnum(x)}</td>"
                f"<td>{who(nm(x['owner_id']))}</td><td class='{red}'>{mdy(ec) if ec else '—'}</td><td class='r'>{money(x['value'] or 0)}</td></tr>")
    TH = '<thead><tr><th>Bid due</th><th>Project</th><th>Proj #</th><th>Owner</th><th>Exp. close</th><th class="r">Amount</th></tr></thead>'
    size = -(-len(props) // n_pp) if props else 0  # spread evenly across the proposal pages
    p3 = ''
    for pg in range(n_pp):
        chunk = props[pg*size:(pg+1)*size]
        half = (len(chunk) + 1) // 2
        colA = ''.join(prow(x) for x in chunk[:half])
        colB = ''.join(prow(x) for x in chunk[half:])
        if pg == n_pp - 1:
            colB += f"<tr class='gt'><td></td><td class='pj'>{len(props)} proposals out</td><td></td><td></td><td></td><td class='r'>{money(prop_v)}</td></tr>"
        part = f' · page {pg+1} of {n_pp}' if n_pp > 1 else ''
        body = (f'<div class="p3"><table class="gr g3">{TH}<tbody>{colA}</tbody></table><table class="gr g3">{TH}<tbody>{colB}</tbody></table></div>'
                if props else "<div class='none'>No open proposals.</div>")
        p3 += f'''<div class="page" id="p{3+pg}">
{hdr('On the Green', f'{name} Proposals Sent')}
<div class="panel" style="margin-top:16px"><div class="ptitle">On the Green · Proposals Sent <small>{len(props)} out · {money(prop_v)} · by bid due date{part}</small></div>
{body}</div>
<div class="foot"><span>Open deals in Proposal Sent · Red close date = earlier than bid date · * Name not confirmed in Pipedrive</span>{dots(3+pg)}</div>
</div>

'''

    head = open(os.path.join(ROOT, 'scripts', 'tv_head.html'), encoding='utf-8').read().replace('{{TITLE}}', f'{name} Leaderboard')
    page = (head + EXTRA_CSS + '</style></head><body><div id="stage">\n\n<div class="page on fin" id="p0"></div>\n\n'
            + p1 + '\n\n' + p2 + '\n\n' + p3 + '</div>\n' + SCRIPT)
    summary = dict(board=b['folder'], open=open_n, open_value=round(open_v), forecast=round(fc), proposals=len(props),
                   proposal_value=round(prop_v), bids_this_week=n_week, past_due=n_past, won=tw, closed=tw + tl)
    return page, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from-dir', help='folder with open.json/won.json/lost.json instead of the live API')
    ap.add_argument('--today', help='YYYY-MM-DD, for testing')
    ap.add_argument('--out', default=ROOT, help='where to write the BU folders')
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(TZ).date()
    open_deals, won, lost = load(args, today.year)
    for b in BOARDS:
        page, summary = render(b, open_deals, won, lost, today)
        os.makedirs(os.path.join(args.out, b['folder']), exist_ok=True)
        with open(os.path.join(args.out, b['folder'], b['file']), 'w', encoding='utf-8') as f:
            f.write(page)
        print(json.dumps(summary))


if __name__ == '__main__':
    main()
