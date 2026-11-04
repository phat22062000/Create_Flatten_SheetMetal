"""Tạo NC cắt laser định dạng CamMagic LA (Mitsubishi) từ DXF trải phôi.
Hỗ trợ biên ngoài LINE + ARC (laser R); lỗ CIRCLE, lỗ dài/lỗ hình (vòng kín LINE + ARC, ngang/đứng), khe cắt (đường hở).
Phôi Y<=100 & X>=1000 có marker TEXT "J" và "LJ" trên biên: đục ngoài tại LJ và J, micro joint tại 2 vị trí này.
Vạch dấu/kegaki: LINE/ARC màu đỏ (ACI color 62='1'), cắt M98P9017, không bù.
Dùng: python3 cammagic_nc.py <file.dxf> <nhóm SS|SUS|AL|CU> <độ dày> [file_ra.nc]
"""
import math, sys, os

def fmt(v):
    v = round(v, 3)
    if abs(v) < 1e-9: v = 0.0
    s = ("%.3f" % v).rstrip('0')          # 21.000 -> "21." ; 46.800 -> "46.8"
    return s

MARKS = {}
KEGAKI = []
KEGAKI_OFFSET = 3.0   # khoảng cách đục ra ngoài biên cho kegaki hở (giả định, xem Quy_tac_NC_CamMagic_LA.md)

def read_dxf(path):
    raw = open(path, 'rb').read().decode('cp932', errors='replace').replace('\r\n', '\n').split('\n')
    pairs = [(raw[i].strip(), raw[i+1].strip()) for i in range(0, len(raw) - 1, 2)]
    ents, cur, on = [], None, False
    for i, (c, v) in enumerate(pairs):
        if c == '2' and v == 'ENTITIES' and pairs[i-1] == ('0', 'SECTION'):
            on = True; continue
        if not on: continue
        if c == '0':
            if cur: ents.append(cur)
            if v == 'ENDSEC': break
            cur = {'type': v}
        elif cur is not None:
            cur.setdefault(c, v)
    segs = [{'t': 'L', 'p': (float(e['10']), float(e['20'])), 'q': (float(e['11']), float(e['21']))}
            for e in ents if e['type'] == 'LINE' and e.get('6', '').upper() != 'DASHED' and e.get('62', '') != '1']
    global KEGAKI   # đường màu đỏ (ACI 62=1) = đường vạch dấu (kegaki, M98P9017), không bù G41
    KEGAKI = [{'t': 'L', 'p': (float(e['10']), float(e['20'])), 'q': (float(e['11']), float(e['21']))}
              for e in ents if e['type'] == 'LINE' and e.get('62', '') == '1']
    for e in ents:   # ARC (laser R): ngược chiều kim đồng hồ từ góc 50 đến góc 51
        if e['type'] == 'ARC':
            cx, cy, r = float(e['10']), float(e['20']), float(e['40'])
            a0, a1 = math.radians(float(e['50'])), math.radians(float(e['51']))
            arc = {'t': 'A', 'c': (cx, cy), 'r': r,
                   'p': (cx + r*math.cos(a0), cy + r*math.sin(a0)),
                   'q': (cx + r*math.cos(a1), cy + r*math.sin(a1)),
                   'sweep': (a1 - a0) % (2*math.pi)}
            if e.get('62', '') == '1': KEGAKI.append(arc)
            else: segs.append(arc)
    circles = [(float(e['10']), float(e['20']), float(e['40'])) for e in ents if e['type'] == 'CIRCLE']
    global MARKS   # TEXT 'J' / 'LJ' (micro joint / piercing ngoài cho phôi dài, hẹp)
    MARKS = {e['1'].strip().upper(): (float(e['10']), float(e['20'])) for e in ents
             if e['type'] == 'TEXT' and e.get('1', '').strip().upper() in ('J', 'LJ')}
    if any(e['type'] in ('LWPOLYLINE', 'POLYLINE', 'SPLINE') for e in ents):
        sys.exit("Biên dạng có POLYLINE/SPLINE: script hiện chỉ hỗ trợ LINE + ARC + CIRCLE")
    return segs, circles

def chain(segs):
    """Nối LINE/ARC thành biên kín, trả về danh sách đoạn có hướng (CW):
    {'t','p','q'(+ 'c','r','ccw' cho ARC)}"""
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    def orient(sg, rev):
        d = dict(sg)
        if rev:
            d['p'], d['q'] = sg['q'], sg['p']
            if sg['t'] == 'A': d['ccw'] = False
        elif sg['t'] == 'A': d['ccw'] = True
        return d
    out, used = [orient(segs[0], False)], {0}
    while len(used) < len(segs):
        for i, sg in enumerate(segs):
            if i in used: continue
            if key(sg['p']) == key(out[-1]['q']): out.append(orient(sg, False)); used.add(i); break
            if key(sg['q']) == key(out[-1]['q']): out.append(orient(sg, True)); used.add(i); break
        else:
            sys.exit("Biên dạng ngoài bị hở")
    if key(out[0]['p']) != key(out[-1]['q']): sys.exit("Biên dạng ngoài không kín")
    def poly(sg):
        if sg['t'] == 'L': return [sg['p']]
        cx, cy = sg['c']; a0 = math.atan2(sg['p'][1]-cy, sg['p'][0]-cx)
        sw = sg['sweep'] if sg['ccw'] else -sg['sweep']
        return [(cx + sg['r']*math.cos(a0 + sw*k/4), cy + sg['r']*math.sin(a0 + sw*k/4)) for k in range(4)]
    pts = [q for sg in out for q in poly(sg)]
    area = sum(pts[i][0]*pts[(i+1) % len(pts)][1] - pts[(i+1) % len(pts)][0]*pts[i][1] for i in range(len(pts))) / 2
    if area > 0:   # đảo sang chiều kim đồng hồ
        out = [orient({**sg, 'p': sg['p'], 'q': sg['q']}, True) if sg['t'] == 'L' else
               {**sg, 'p': sg['q'], 'q': sg['p'], 'ccw': not sg['ccw']} for sg in reversed(out)]
        out = [dict(sg, p=sg['p'], q=sg['q']) for sg in out]
    return out

# (piercing ngoài, joint ngoài, piercing lỗ) theo Quy_tac_laser_kim_loai_tam.md mục 2
TABLE = {
    'SS':  [(3.2, (3, 0.8, 6)), (5, (6, 1, 6)), (9, (6, 1, 6)), (16, (10, 1, 10))],
    'SUS': [(8, (6, 0.7, 6)), (16, (10, 1, 10))],
    'AL':  [(8, (6, 0.7, 6)), (18, (10, 1, 10))],
    'CU':  [(99, (6, 0.7, 6))],
}

def params(group, t):
    for tmax, p in TABLE[group.upper()]:
        if t <= tmax + 1e-9: return p
    sys.exit("Độ dày %s của nhóm %s dùng piercing cong (≥19t): script chưa hỗ trợ" % (t, group))

def group_loops(segs):
    """Tách các đoạn LINE/ARC thành các vòng kín riêng (biên ngoài + lỗ dài/lỗ hình)."""
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    par = list(range(len(segs)))
    def f(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    first = {}
    for i, g in enumerate(segs):
        for k in (key(g['p']), key(g['q'])):
            if k in first: par[f(i)] = f(first[k])
            else: first[k] = i
    grp = {}
    for i in range(len(segs)): grp.setdefault(f(i), []).append(segs[i])
    return list(grp.values())

def is_open(L):
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    deg = {}
    for g in L:
        for k in (key(g['p']), key(g['q'])): deg[k] = deg.get(k, 0) + 1
    return any(v == 1 for v in deg.values())

def inside(pt, loop):
    """Điểm nằm trong biên ngoài (đa giác xấp xỉ, cung lấy thêm điểm giữa)."""
    pts = []
    for g in loop:
        pts.append(g['p'])
        if g['t'] == 'A':
            cx, cy = g['c']; a0 = math.atan2(g['p'][1]-cy, g['p'][0]-cx)
            sw = g['sweep'] if g['ccw'] else -g['sweep']
            pts.append((cx + g['r']*math.cos(a0+sw/2), cy + g['r']*math.sin(a0+sw/2)))
    x, y = pt; c = False
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i], pts[(i+1) % len(pts)]
        if (y1 > y) != (y2 > y) and x < x1 + (y-y1)*(x2-x1)/(y2-y1): c = not c
    return c

def order_open(L, outer):
    """Khe cắt (đường hở): bắt đầu ở đầu nằm ngoài chi tiết (phía phế liệu), trả về dãy đoạn có hướng."""
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    deg = {}
    for g in L:
        for p in (g['p'], g['q']): deg.setdefault(key(p), []).append(p)
    ends = [v[0] for v in deg.values() if len(v) == 1]
    if len(ends) != 2: sys.exit("Khe cắt không phải 1 đường hở đơn")
    out_e = [e for e in ends if not inside(e, outer)]
    start = out_e[0] if len(out_e) == 1 else ends[0]
    seq, cur, rest = [], start, list(L)
    while rest:
        for g in rest:
            if key(g['p']) == key(cur):
                seq.append(dict(g, ccw=True) if g['t'] == 'A' else dict(g)); cur = g['q']; rest.remove(g); break
            if key(g['q']) == key(cur):
                d = dict(g, p=g['q'], q=g['p'])
                if g['t'] == 'A': d['ccw'] = False
                seq.append(d); cur = g['p']; rest.remove(g); break
        else:
            sys.exit("Khe cắt bị đứt")
    return start, seq

def rev(loop):
    return [dict(g, p=g['q'], q=g['p'], **({'ccw': not g['ccw']} if g['t'] == 'A' else {})) for g in reversed(loop)]

def loop_area(loop):
    """Diện tích có dấu (dương = CCW), tính chính xác cả phần cung."""
    s = 0.0
    for g in loop:
        s += g['p'][0]*g['q'][1] - g['q'][0]*g['p'][1]
    s /= 2
    for g in loop:
        if g['t'] == 'A':
            seg = g['r']**2 / 2 * (g['sweep'] - math.sin(g['sweep']))
            s += seg if g['ccw'] else -seg
    return s

def split_at_left(loop):
    """Xoay vòng (CCW) để bắt đầu tại điểm vào (trái nhất nếu lỗ nằm ngang, thấp nhất nếu lỗ
    đứng - theo trục dài của lỗ); cắt đôi cung/đoạn nếu cần.
    Trả về (danh sách đoạn, điểm bắt đầu, bán kính cung tại điểm đầu hoặc None, trục 0=X/1=Y)."""
    xs = [v for g in loop for v in (g['p'][0], g['q'][0])]
    ys = [v for g in loop for v in (g['p'][1], g['q'][1])]
    ax = 0 if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else 1   # 0=X (ngang), 1=Y (đứng)
    target = math.pi if ax == 0 else -math.pi/2   # trái nhất (ax=0) hoặc thấp nhất (ax=1)
    best = None
    for i, g in enumerate(loop):
        cand = [(g['p'], None)]
        if g['t'] == 'A':
            cx, cy = g['c']; ap = math.atan2(g['p'][1]-cy, g['p'][0]-cx)
            d = (target - ap) % (2*math.pi) if g['ccw'] else (ap - target) % (2*math.pi)
            if 1e-9 < d < g['sweep'] - 1e-9:
                pt = (cx + g['r']*math.cos(target), cy + g['r']*math.sin(target))
                cand.append((pt, d))
        elif ax == 0 and abs(g['p'][0]-g['q'][0]) < 1e-9:
            cand.append((((g['p'][0]+g['q'][0])/2, (g['p'][1]+g['q'][1])/2), 'mid'))
        elif ax == 1 and abs(g['p'][1]-g['q'][1]) < 1e-9:
            cand.append((((g['p'][0]+g['q'][0])/2, (g['p'][1]+g['q'][1])/2), 'mid'))
        for pt, extra in cand:
            k = (round(pt[ax], 6), 0 if extra is not None else 1)
            if best is None or k < best[0]: best = (k, i, pt, extra)
    _, i, pt, extra = best
    g = loop[i]
    if extra is None:
        out = loop[i:] + loop[:i]; r = None
    elif g['t'] == 'A':
        g1 = dict(g, q=pt, sweep=extra); g2 = dict(g, p=pt, sweep=g['sweep']-extra)
        out = [g2] + loop[i+1:] + loop[:i] + [g1]; r = g['r']
    else:
        out = [dict(g, p=pt)] + loop[i+1:] + loop[:i] + [dict(g, q=pt)]; r = None
    return out, pt, r, ax

def on_seg(g, pt, tol=1e-3):
    if g['t'] != 'L': return False
    (x1, y1), (x2, y2) = g['p'], g['q']
    L = math.dist(g['p'], g['q'])
    if L < 1e-9: return False
    t = ((pt[0]-x1)*(x2-x1) + (pt[1]-y1)*(y2-y1)) / L**2
    cx, cy = x1 + t*(x2-x1), y1 + t*(y2-y1)
    return -1e-9 <= t <= 1 + 1e-9 and math.dist(pt, (cx, cy)) < tol

def split_path(sg, M, E, joint, pierce_out):
    """Phoi dai hep (Y<=100, X>=1000) co marker LJ/J tren bien: bien ngoai (CW) tach thanh 2 duong,
    moi duong bat dau tai marker M (duc ngoai, vuong goc voi canh) va dung truoc marker E mot doan joint.
    Tra ve (diem duc, day doan tu M toi diem dung)."""
    iM = next(i for i, g in enumerate(sg) if on_seg(g, M))
    g = sg[iM]
    dx, dy = g['q'][0]-g['p'][0], g['q'][1]-g['p'][1]; ln = math.hypot(dx, dy)
    nrm = (-dy/ln, dx/ln)                                  # phap tuyen ngoai (CW -> ben trai huong chay)
    seq = [dict(g, p=M)] + sg[iM+1:] + sg[:iM] + [dict(g, q=M)]
    seq = [x for x in seq if not (x['t'] == 'L' and math.dist(x['p'], x['q']) < 1e-6)]
    out = []
    for x in seq:                                          # cat toi E
        if on_seg(x, E):
            out.append(dict(x, q=E)); break
        out.append(x)
    last = out[-1]
    if last['t'] != 'L' or math.dist(last['p'], last['q']) <= joint:
        sys.exit("Marker J/LJ: doan cuoi truoc joint khong phai doan thang du dai")
    ux, uy = (last['q'][0]-last['p'][0]), (last['q'][1]-last['p'][1]); l2 = math.hypot(ux, uy)
    last['q'] = (E[0] - ux/l2*joint, E[1] - uy/l2*joint)
    return (M[0] + nrm[0]*pierce_out, M[1] + nrm[1]*pierce_out), out

def chain_open_from(L, start_pt):
    """Nối các đoạn của 1 đường hở thành dãy có hướng, bắt đầu từ start_pt (1 trong 2 đầu hở)."""
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    seq, cur, rest = [], start_pt, list(L)
    while rest:
        for g in rest:
            if key(g['p']) == key(cur):
                seq.append(dict(g, ccw=True) if g['t'] == 'A' else dict(g)); cur = g['q']; rest.remove(g); break
            if key(g['q']) == key(cur):
                d = dict(g, p=g['q'], q=g['p'])
                if g['t'] == 'A': d['ccw'] = False
                seq.append(d); cur = g['p']; rest.remove(g); break
        else:
            sys.exit("Đường vạch dấu (kegaki) bị đứt")
    return seq

def build_kegaki(bbox):
    """Nhóm các đoạn kegaki (màu đỏ) thành từng đường, xác định điểm đục.
    Vòng kín: đục tại đỉnh gần gốc (0,0) nhất, chạy theo chiều kim đồng hồ, không bù, khép kín.
    Đường hở: đục ngoài biên (lệch KEGAKI_OFFSET khỏi cạnh ngoài tại đầu hở), chọn đầu có điểm đục gần gốc (0,0) hơn.
    Trả về list (điểm đục, dãy đoạn để emit(), không bù G41), đã sắp theo khoảng cách điểm đục tới gốc."""
    xmin, xmax, ymin, ymax = bbox
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    out = []
    for L in group_loops(KEGAKI):
        if not is_open(L):
            seq = chain(L)                       # CW, khép kín
            best = min(range(len(seq)), key=lambda i: math.hypot(*seq[i]['p']))
            seq = seq[best:] + seq[:best]
            start = seq[0]['p']
            out.append((start, seq))
        else:
            deg = {}
            for g in L:
                for p in (g['p'], g['q']): deg.setdefault(key(p), []).append(p)
            ends = [v[0] for v in deg.values() if len(v) == 1]
            if len(ends) != 2: sys.exit("Đường vạch dấu (kegaki) không phải 1 đường hở đơn")
            cands = []
            for e in ends:
                if abs(e[0] - xmin) < 1e-6: ext = (xmin - KEGAKI_OFFSET, e[1])
                elif abs(e[0] - xmax) < 1e-6: ext = (xmax + KEGAKI_OFFSET, e[1])
                elif abs(e[1] - ymin) < 1e-6: ext = (e[0], ymin - KEGAKI_OFFSET)
                elif abs(e[1] - ymax) < 1e-6: ext = (e[0], ymax + KEGAKI_OFFSET)
                else: ext = e   # đầu hở không chạm biên ngoài: không rõ hướng đục, không mở rộng
                cands.append((ext, e))
            ext, e0 = min(cands, key=lambda c: math.hypot(*c[0]))
            lead = {'t': 'L', 'p': ext, 'q': e0}
            seq = [lead] + chain_open_from(L, e0)
            out.append((ext, seq))
    out.sort(key=lambda z: math.hypot(*z[0]))
    return out

def emit(segs, prev, body):
    """Ghi G01/G02/G03 cho dãy đoạn có hướng; trả về (độ dài cắt, điểm cuối)."""
    cut = 0.0
    for g in segs:
        q = g['q']
        if g['t'] == 'L':
            body.append("G01X%sY%s" % (fmt(q[0]), fmt(q[1]))); cut += math.dist(prev, q)
        else:   # ARC: G03 ngược chiều kim đồng hồ, G02 cùng chiều; I/J = tâm - điểm đầu (bỏ số 0)
            i_, j_ = g['c'][0]-prev[0], g['c'][1]-prev[1]
            w = ("G03" if g['ccw'] else "G02") + "X%sY%s" % (fmt(q[0]), fmt(q[1]))
            if abs(round(i_, 3)) > 1e-9: w += "I" + fmt(i_)
            if abs(round(j_, 3)) > 1e-9: w += "J" + fmt(j_)
            body.append(w); cut += g['r'] * g['sweep']
        prev = q
    return cut, prev

def build(dxf, group, t):
    pierce_out, joint_out, pierce_hole = params(group, t)
    segs, circles = read_dxf(dxf)
    if group.upper() != 'SS' and any(2*c[2] >= 50 for c in circles):
        sys.exit("Có lỗ ≥ φ50 trên SUS/AL/CU cần joint lỗ: script chưa hỗ trợ")
    loops = group_loops(segs)
    bb = lambda L: (max(max(g['p'][0], g['q'][0]) for g in L) - min(min(g['p'][0], g['q'][0]) for g in L)) * \
                   (max(max(g['p'][1], g['q'][1]) for g in L) - min(min(g['p'][1], g['q'][1]) for g in L))
    opens = [L for L in loops if is_open(L)]          # khe cắt (スリット): đường hở
    loops = [L for L in loops if not is_open(L)]
    loops.sort(key=bb, reverse=True)
    sg = chain(loops[0])                       # biên ngoài (CW)
    slits = [order_open(L, sg) for L in opens]
    holes = []                                 # mỗi lỗ: (diện tích, điểm đục, điểm vào, dãy đoạn CCW)
    for cx, cy, r in circles:
        px = cx if r < pierce_hole else cx - r + pierce_hole   # bán kính < piercing -> đục tâm
        holes.append((math.pi*r*r, (px, cy), (cx-r, cy),
                      [{'t': 'A', 'c': (cx, cy), 'r': r, 'p': (cx-r, cy), 'q': (cx-r, cy), 'sweep': 2*math.pi, 'ccw': True}]))
    for L in loops[1:]:                        # lỗ dài / lỗ hình (LINE + ARC)
        L = chain(L)                           # CW
        L = rev(L)                             # lỗ cắt CCW (G03)
        A = loop_area(L)
        L, st, r, ax = split_at_left(L)
        w = max(max(g['p'][ax], g['q'][ax]) for g in L) - st[ax]
        dpi = r if (r is not None and r < pierce_hole) else min(pierce_hole, w / 2)
        pp = (st[0] + dpi, st[1]) if ax == 0 else (st[0], st[1] + dpi)
        holes.append((abs(A), pp, st, L))

    split_mode = 'J' in MARKS and 'LJ' in MARKS
    _bx = [g['p'][0] for g in sg] + [g['q'][0] for g in sg]; _by = [g['p'][1] for g in sg] + [g['q'][1] for g in sg]
    if not split_mode and max(_by)-min(_by) <= 100 and max(_bx)-min(_bx) >= 1000:
        print("CANH BAO: phoi Y<=100, X>=1000 nhung DXF khong co marker J/LJ - dang dung piercing canh trai thuong", file=sys.stderr)
    xmin = min(min(g['p'][0], g['q'][0]) for g in sg if g['t'] == 'L')
    # điểm vào biên ngoài: trên đoạn thẳng đứng dài nhất nằm ở X nhỏ nhất (cạnh trái)
    cand = [(abs(g['q'][1]-g['p'][1]), i) for i, g in enumerate(sg)
            if g['t'] == 'L' and abs(g['p'][0]-xmin) < 1e-6 and abs(g['q'][0]-xmin) < 1e-6]
    if split_mode: cand = cand or [(0, 0)]
    if not cand:
        sys.exit("Không có cạnh thẳng đứng ở X nhỏ nhất: xoay DXF (90/180/270, không lật) trước khi tạo NC")
    _, i0 = max(cand)
    a, b = sg[i0]['p'], sg[i0]['q']
    d = 1 if b[1] > a[1] else -1                 # hướng chạy trên cạnh trái (CW: đi lên)
    # vị trí piercing ngoài theo chiều dài cạnh trái L:
    #   L <= 100 -> giữa cạnh ; L > 100 -> cách đầu dưới của cạnh 40
    Lr = abs(b[1] - a[1])
    bottom = False
    if Lr < 10 and not split_mode:
        # cạnh thẳng theo Oy quá ngắn (<10, không tính vát C/bo R): đục piercing ngoài tại cạnh nằm trên Ox,
        # cách đầu trái của đoạn thẳng 40 (không tính vát C/bo R)
        ymin_ = min(g['p'][1] for g in sg)
        cb = [(abs(g['q'][0]-g['p'][0]), k) for k, g in enumerate(sg)
              if g['t'] == 'L' and abs(g['p'][1]-ymin_) < 1e-6 and abs(g['q'][1]-ymin_) < 1e-6]
        if not cb: sys.exit("Không có cạnh thẳng trên Ox để đục piercing ngoài")
        Lb, i0 = max(cb)
        a, b = sg[i0]['p'], sg[i0]['q']
        xl = min(a[0], b[0]); off = min(40.0, Lb / 2)
        start = (xl + off, ymin_); bottom = True
        dx_ = (b[0]-a[0]) / Lb
        end = (start[0] - dx_*joint_out, ymin_)
    else:
        sy = (a[1] + b[1]) / 2 if Lr <= 100 + 1e-9 else min(a[1], b[1]) + 40
        start = (xmin, sy)
        end = (xmin, sy - d*joint_out)
    seq = [sg[(i0+k) % len(sg)] for k in range(1, len(sg))]   # các đoạn sau cạnh vào, kết thúc tại a
    ys = [g['p'][1] for g in sg] + [g['q'][1] for g in sg]
    xs0 = [g['p'][0] for g in sg] + [g['q'][0] for g in sg]

    cut, rapid, beam = 0.0, 0.0, 0
    # lỗ: diện tích nhỏ nhất -> lớn nhất; cùng diện tích thì chọn lỗ có điểm đục gần nhất
    rem = sorted(holes, key=lambda h: h[0])
    order, cur = [], (0.0, 0.0)
    while rem:
        amin = rem[0][0]
        grp = [h for h in rem if abs(h[0] - amin) < 1e-3]
        h = min(grp, key=lambda h: math.dist(cur, h[1]))
        order.append(h); rem.remove(h); cur = h[2]
    body, pos = [], (0.0, 0.0)
    # kegaki (vạch dấu, màu đỏ) trước tiên: không bù, mã M98P9017
    kegaki_list = build_kegaki((min(xs0), max(xs0), min(ys), max(ys))) if KEGAKI else []
    for pp_, seq_ in kegaki_list:
        rapid += math.dist(pos, pp_)
        body += ["G00X%sY%sG40" % (fmt(pp_[0]), fmt(pp_[1])), "M98P9017"]
        c_, end_ = emit(seq_, pp_, body); cut += c_
        body += ["M121", "M199"]
        pos = end_; beam += 1
        xs0.append(pp_[0]); ys.append(pp_[1])
    # khe cắt trước: đục tại đầu ngoài phía phế liệu, không bù, không dẫn vào; gần nhất trước
    rem_s = list(slits); cur_s = (0.0, 0.0)
    while rem_s:
        st_, seq_ = min(rem_s, key=lambda z: math.dist(cur_s, z[0])); rem_s.remove((st_, seq_))
        rapid += math.dist(pos, st_)
        body += ["G00X%sY%sG40" % (fmt(st_[0]), fmt(st_[1])), "M98P9010"]
        c_, end_ = emit(seq_, st_, body); cut += c_
        body += ["M121", "M199"]
        pos = cur_s = end_; beam += 1
    for _, pp_, st, L in order:
        rapid += math.dist(pos, pp_)
        body += ["G00X%sY%sG40" % (fmt(pp_[0]), fmt(pp_[1])), "M98P9010",
                 "G01G41X%sY%s" % (fmt(st[0]), fmt(st[1]))]
        cut += math.dist(pp_, st)
        if len(L) == 1 and L[0]['sweep'] >= 2*math.pi - 1e-9:      # lỗ tròn
            r = L[0]['r']
            body.append("G03X%sY%sI%s" % (fmt(st[0]), fmt(st[1]), fmt(r))); cut += 2*math.pi*r
        else:
            c_, _ = emit(L, st, body); cut += c_
        body += ["M121", "M199"]
        pos = st; beam += 1
    if split_mode:
        paths = [split_path(sg, MARKS['LJ'], MARKS['J'], joint_out, pierce_out),
                 split_path(sg, MARKS['J'], MARKS['LJ'], joint_out, pierce_out)]
        pps = []
        for k, (pp_, seq_) in enumerate(paths):
            M = seq_[0]['p']
            rapid += math.dist(pos, pp_)
            body += ["G00X%sY%sG40" % (fmt(pp_[0]), fmt(pp_[1])), "M98P9010",
                     "G01G41X%sY%s" % (fmt(M[0]), fmt(M[1]))]
            cut += pierce_out
            c_, prev = emit(seq_, M, body); cut += c_
            body += ["M121", "M199"]
            if k == 1: body += ["G01G40", "M30"]
            pos = prev; beam += 1; pps.append(pp_)
        pp = pps[0]
        xs0 = xs0 + [p[0] for p in pps]; ys = ys + [p[1] for p in pps]
    else:
        pp = (start[0], start[1] - pierce_out) if bottom else (xmin - pierce_out, sy)
        if bottom: ys.append(pp[1])
        rapid += math.dist(pos, pp)
        body += ["G00X%sY%sG40" % (fmt(pp[0]), fmt(pp[1])), "M98P9010",
                 "G01G41X%sY%s" % (fmt(start[0]), fmt(start[1]))]
        cut += pierce_out
        body.append("G01X%sY%s" % (fmt(b[0]), fmt(b[1]))); cut += math.dist(start, b)
        c_, prev = emit(seq, b, body); cut += c_
        body.append("G01X%sY%s" % (fmt(end[0]), fmt(end[1]))); cut += math.dist(prev, end)
        body += ["M121", "M199", "G01G40", "M30"]
        beam += 1

    xs = xs0 + ([pp[0]] if not split_mode else [])
    name = os.path.basename(dxf)
    code = name.split('_')[-1].rsplit('.', 1)[0] if '_' in name else name.rsplit('.', 1)[0]
    head = ["(#_)%(#_)",
            "(%s.DXF / %.1f X %.1f)" % (code, max(xs)-min(xs), max(ys)-min(ys)),
            "#501=106", "M66", "G90", "G92X0.Y0."]
    tail = ["(CUTTING_LENGTH = %8.1fMM  RAPID_LENGTH = %8.1fMM)" % (cut, rapid),
            "(TOTAL_LENGTH = %8.1fMM)" % (cut + rapid),
            "(BEAM_ON = %d  KEGAKI_ON = 0  PREPIERCE_ON = 0)" % beam,
            "(#_)%(#_)"]
    return code, "\r\n".join(head + body + tail)

if __name__ == "__main__":
    dxf, group, t = sys.argv[1], sys.argv[2], float(sys.argv[3])
    code, txt = build(dxf, group, t)
    outp = sys.argv[4] if len(sys.argv) > 4 else code + ".nc"
    open(outp, "w", newline="").write(txt)
    print(outp)
