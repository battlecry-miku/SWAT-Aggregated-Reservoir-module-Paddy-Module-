# -*- coding: utf-8 -*-
"""Preflight check for SWAT+ TxtInOut folders used in the OFR aggregation study.

Reads input files only -- does not run SWAT+.  Run it after every configuration
change and before any long run:

    python preflight_check.py <TxtInOut> [<TxtInOut> ...]

With several folders it also checks the cross-scenario invariants (total OFR
capacity, interception fraction and parameter files must be identical).
Exit code 1 if any FAIL.
"""
import sys, io, os, hashlib
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CANAL_TOTAL_M3 = 518e6         # canal head capacity, m3/a; fixed-import controls use a smaller quota
if '--canal' in sys.argv:      # --canal <Mm3/a>, stripped here so the folder list stays positional
    _i = sys.argv.index('--canal')
    CANAL_TOTAL_M3 = float(sys.argv[_i + 1]) * 1e6
    del sys.argv[_i:_i + 2]

V_TOTAL_HAM = 5650.36          # total OFR principal volume, ha-m (56.50 Mm3)
F_KAPPA10 = 0.139              # area-weighted interception fraction for kappa = 10
PADDY_SHARE = 53.7             # % of basin, Zhu Xu thesis p21
DRY_SHARE = 5.8
BASIN_HA = 157785.0
BIG_OUTPUTS = ['wetland_day.txt', 'reservoir_day.txt', 'fort.100100', 'water_allo_mon.txt']
PARAM_FILES = ['hydrology.hyd', 'soils.sol', 'aquifer.aqu', 'parameters.bsn',
               'codes.bsn', 'calibration.cal', 'hyd-sed-lte.cha', 'topography.hyd']


def lines(d, fn, skip=0):
    p = os.path.join(d, fn)
    if not os.path.exists(p):
        return None
    with open(p, errors='ignore') as f:
        return [l.split() for l in f.readlines()[skip:]]


class Report:
    def __init__(self, name):
        self.name, self.rows = name, []

    def add(self, level, item, value, hint=''):
        self.rows.append((level, item, value, hint))

    def show(self):
        print('\n' + '=' * 78)
        print(self.name)
        print('=' * 78)
        for lv, it, val, hint in self.rows:
            print('  [%-4s] %-26s %s' % (lv, it, val))
            if hint and lv in ('FAIL', 'WARN'):
                print('         %-26s -> %s' % ('', hint))

    def fails(self):
        return sum(1 for r in self.rows if r[0] == 'FAIL')


# ----------------------------------------------------------------- parsers
def parse_wro(d):
    rows = lines(d, 'water_allocation.wro')
    if rows is None:
        return None
    out = []
    for t in rows:
        if len(t) < 10 or not t[0].isdigit() or not t[1].startswith(('dtbl', 'ave')):
            continue
        try:
            n = int(t[5])
        except ValueError:
            continue
        srcs = [t[7 + 8 * k: 15 + 8 * k] for k in range(n)]
        rcv = t[7 + 8 * n: 10 + 8 * n]
        out.append({'typ': t[1], 'name': t[2], 'amount': t[3], 'srcs': srcs, 'rcv': rcv})
    return out


def parse_res(d):
    # A0 keeps hydrology.res on disk but switches reservoir.con off in file.cio -> no OFR objects
    cio = lines(d, 'file.cio', 0) or []
    con = next((t for t in cio if t[:1] == ['connect']), None)
    if con is not None and 'reservoir.con' not in con:
        return {}
    rows = lines(d, 'hydrology.res', 2)
    if rows is None:
        return {}
    res = {}
    for t in rows:
        if len(t) >= 7:
            try:
                res[t[0]] = (float(t[3]), float(t[4]))
            except ValueError:
                pass
    return res


def parse_rtu(d):
    rows = lines(d, 'rout_unit.con', 2) or []
    out = []
    for t in rows:
        try:
            area = float(t[3])
        except (ValueError, IndexError):
            continue
        fr = 0.0
        for i, v in enumerate(t):
            if v == 'res' and i + 3 < len(t):
                try:
                    fr = float(t[i + 3])
                except ValueError:
                    pass
                break
        out.append((area, fr))
    return out


def parse_landuse(d):
    lum = {}
    for t in lines(d, 'landuse.lum', 2) or []:
        if len(t) >= 4:
            lum[t[0]] = (t[2], t[3])
    hdr = lines(d, 'hru-data.hru', 1)
    hru_lu = {}
    if hdr:
        cols = hdr[0]
        ilu = cols.index('lu_mgt') if 'lu_mgt' in cols else 5
        for t in hdr[1:]:
            if len(t) > ilu and t[0].isdigit():
                hru_lu[int(t[0])] = t[ilu]
    area = {}
    for t in lines(d, 'hru.con', 2) or []:
        try:
            area[int(t[0])] = float(t[3])
        except (ValueError, IndexError):
            pass
    return lum, hru_lu, area


def parse_mgt(d):
    """rotation name -> list of (op, month, day, crop)."""
    rows = lines(d, 'management.sch', 2) or []
    rot, cur, remaining_auto = {}, None, 0
    for t in rows:
        if not t:
            continue
        if len(t) == 3 and not t[0] in ('plnt', 'hvkl', 'harv', 'kill', 'irrm', 'fert', 'till'):
            try:
                int(t[1]); int(t[2])
                cur = t[0]; rot[cur] = []; remaining_auto = int(t[2])
                continue
            except ValueError:
                pass
        if cur is None:
            continue
        if remaining_auto > 0 and len(t) == 1:
            remaining_auto -= 1
            rot[cur].append(('auto', 0, 0, t[0]))
            continue
        if len(t) >= 5 and t[0] in ('plnt', 'hvkl', 'harv', 'kill'):
            try:
                rot[cur].append((t[0], int(t[1]), int(t[2]), t[4]))
            except ValueError:
                pass
    return rot


def md5(d, fn):
    p = os.path.join(d, fn)
    if not os.path.exists(p):
        return None
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:10]


# ----------------------------------------------------------------- checks
def check_folder(d):
    R = Report(d)
    summary = {}

    # time window
    ts = lines(d, 'time.sim', 2)
    if ts and ts[0]:
        y0, y1 = ts[0][1], ts[0][3]
        R.add('INFO', '模拟时段', '%s–%s' % (y0, y1),)
        summary['years'] = (y0, y1)

    # OFR capacity
    res = parse_res(d)
    vol = sum(v for _, v in res.values())
    summary['vol'] = vol
    summary['n_res'] = len(res)
    if not res:
        R.add('INFO', '塘坝对象', '0 个（A0 应为此状态）')
    else:
        ok = abs(vol - V_TOTAL_HAM) / V_TOTAL_HAM < 0.005
        R.add('PASS' if ok else 'FAIL', '塘坝总库容',
              '%d 个对象, Σvol_ps = %.2f ha-m = %.2f Mm3' % (len(res), vol, vol / 100),
              '应为 %.2f ha-m (56.50 Mm3)；检查是否误用了放大库容或常数库深' % V_TOTAL_HAM)

    # interception fraction
    rtu = parse_rtu(d)
    if rtu and res:
        con = [x for x in rtu if x[1] > 0]          # only units routed to an OFR
        a = sum(x[0] for x in con)
        fw = sum(x[0] * x[1] for x in con) / a if a else 0
        frs = [x[1] for x in rtu if x[1] > 0]
        uniform = len(set(round(f, 4) for f in frs)) <= 1
        summary['f'] = fw
        if uniform and frs and abs(frs[0] - 0.06) < 1e-4:
            R.add('WARN', '汇水拦截比例 f', '全部单元 = 0.060（均一旧配置）',
                  '补充2：按 f_i = min(1, κ·A_res/A_rtu) 逐单元设定，κ = 10 时面积加权应为 0.139')
        else:
            R.add('INFO', '汇水拦截比例 f', '面积加权 = %.4f；范围 %.3f–%.3f；%d 个单元'
                  % (fw, min(frs) if frs else 0, max(frs) if frs else 0, len(frs)))

    # water allocation
    wro = parse_wro(d)
    lum, hru_lu, area = parse_landuse(d)
    if wro is None:
        R.add('INFO' if not res else 'WARN', '水量分配文件', '无 water_allocation.wro',
              '含塘情景需要水量分配；A0 需确认稻田灌溉水源')
    else:
        paddy = [r for r in wro if r['typ'] == 'dtbl_lum']
        topup = [r for r in wro if r['typ'] == 'dtbl_con']
        n_unl = sum(1 for r in paddy for s in r['srcs'] if s and s[0] == 'unl')
        nres_obj = len(res)
        bad_ref = [(r['name'], s[1]) for r in wro for s in r['srcs'] if s and s[0] == 'res'
                   and not (1 <= int(s[1]) <= nres_obj)]
        bad_ref += [(r['name'], r['rcv'][1]) for r in wro if len(r['rcv']) >= 2 and r['rcv'][0] == 'res'
                    and not (1 <= int(r['rcv'][1]) <= nres_obj)]
        R.add('PASS' if not bad_ref else 'FAIL', '塘坝编号引用有效',
              '供水/补水记录引用的塘坝编号均在 1–%d 内' % nres_obj if not bad_ref
              else '%d 处越界，例：%s' % (len(bad_ref), bad_ref[:3]),
              '供水连接指向了不存在的塘坝对象：配置未按该尺度重新生成')
        # A0 (no OFR objects): channel first, then direct canal water (unl) under the canal cap
        a0_canal = nres_obj == 0 and paddy and all(
            len(r['srcs']) == 2 and r['srcs'][0][0] == 'cha' and r['srcs'][1][0] == 'unl' for r in paddy)
        if a0_canal:
            R.add('PASS', '稻田无限源兜底', 'A0：%d 条稻田均为 河道 → 渠道直灌(unl)，受 518 额度约束（需补丁 exe）'
                  % len(paddy))
        else:
            R.add('PASS' if n_unl == 0 else 'FAIL', '稻田无限源兜底',
                  '%d 条稻田取水记录，其中 %d 条含 unl 源' % (len(paddy), n_unl),
                  '补充3：稻田取水改为 塘坝优先 → 河道(cha)补缺，取消 unl')
        second = 'unl' if a0_canal else 'cha'
        bad = []
        for r in paddy:
            s = r['srcs']
            if len(s) >= 2:
                s2 = s[1]
                if not (len(s2) >= 8 and s2[0] == second and s2[7] == 'y'):
                    bad.append(r)
                elif abs(float(s2[6])) > 1e-6:
                    bad.append(r)
        if paddy:
            R.add('PASS' if not bad else 'FAIL', '稻田第二水源写法',
                  '%d/%d 条符合 %s, frac=0, comp=y' % (len(paddy) - len(bad), len(paddy), second),
                  'frac 须为 0、comp 须为 y，否则会重复请求一整份需求（agent 查源码所得）')
        if a0_canal:
            cap = sum(float(r['amount']) for r in paddy)
            ok = abs(cap - CANAL_TOTAL_M3) / CANAL_TOTAL_M3 < 1e-3
            R.add('PASS' if ok else 'FAIL', 'A0 渠道直灌额度合计',
                  '%.1f Mm3（应为 %.0f）' % (cap / 1e6, CANAL_TOTAL_M3 / 1e6),
                  '按稻田面积分配 %.0f Mm3/a（固定引水对照用 --canal 指定）' % (CANAL_TOTAL_M3 / 1e6))
        amt = 0.0
        for r in topup:
            try:
                amt += float(r['amount'])
            except ValueError:
                pass
        if topup:
            R.add('PASS' if amt > 0 else 'WARN', '渠道补水封顶',
                  '%d 条补水记录, Σamount = %.4g' % (len(topup), amt),
                  '补充3：外调水全流域 ≤ 518 Mm3/a；amount 全为 0 表示未设单条上限')
        # receivers must be rice HRUs
        rcv_h = [int(r['rcv'][1]) for r in paddy if len(r['rcv']) >= 2 and r['rcv'][0] == 'hru']
        rice_lums = {k for k, (pc, mg) in lum.items() if 'rice' in pc.lower() or 'rice' in mg.lower()}
        non_rice = [h for h in rcv_h if hru_lu.get(h) not in rice_lums]
        if rcv_h:
            R.add('PASS' if not non_rice else 'FAIL', '取水受水端均为稻田',
                  '%d 个受水 HRU，其中非稻田 %d 个' % (len(rcv_h), len(non_rice)),
                  '只有水田 HRU 应从塘坝取水，旱地不连接')

    # irrigation op referenced by paddy decision tables must exist with eff > 0
    if wro:
        irr = {}
        for t in lines(d, 'irr.ops', 2) or []:
            if len(t) >= 3:
                try:
                    irr[t[0]] = float(t[2])
                except ValueError:
                    pass
        dtbl_opt, cur = {}, None
        for t in lines(d, 'lum.dtl') or []:
            if len(t) == 4 and t[1].isdigit() and t[2].isdigit() and t[3].isdigit():
                cur = t[0]
            elif cur and len(t) >= 5 and t[0] in ('irr_wallo', 'irrigate') and cur not in dtbl_opt:
                dtbl_opt[cur] = t[4]
        names = sorted({r['name'] for r in wro if r['typ'] == 'dtbl_lum'})
        for nm in names:
            opt = dtbl_opt.get(nm)
            eff = irr.get(opt)
            ok = eff is not None and eff > 0
            R.add('PASS' if ok else 'FAIL', '灌溉到田效率 (%s)' % nm,
                  '方式 %s → eff = %s' % (opt, 'irr.ops 中不存在' if eff is None else '%.2f' % eff),
                  '效率为 0 时取走的水不会落到田里（源码默认 eff = 0）：在 irr.ops 补该方式并设 eff > 0')

    # canal top-up tables must reset the shared demand variable (stale trn_m3 bug)
    tabs, cur = {}, None
    for t in lines(d, 'flo_con.dtl') or []:
        if len(t) == 4 and t[0].startswith('topup_res') and t[1].isdigit():
            cur = t[0]; tabs[cur] = []
        elif cur and t and t[0] == 'res_demand' and len(t) >= 6:
            try:
                tabs[cur].append(float(t[5]))
            except ValueError:
                pass
    if tabs:
        guarded = sum(1 for v in tabs.values() if len(v) >= 2 and v[0] == 0.0)
        R.add('PASS' if guarded == len(tabs) else 'FAIL', '补水需求清零保护',
              '%d/%d 张补水表首个动作为清零' % (guarded, len(tabs)),
              '决策表未命中时 trn_m3 沿用旧值：须先加 const=0 的 res_demand 动作（永远命中的备选）')

    # land use shares
    if hru_lu and area:
        agg = defaultdict(float)
        for h, a in area.items():
            agg[hru_lu.get(h, '?')] += a
        tot = sum(agg.values())
        rice_lums = {k for k, (pc, mg) in lum.items() if 'rice' in pc.lower() or 'rice' in mg.lower()}
        rice_a = sum(v for k, v in agg.items() if k in rice_lums)
        share = 100 * rice_a / tot if tot else 0
        summary['rice_share'] = share
        ok = abs(share - PADDY_SHARE) <= 2.0
        R.add('PASS' if ok else 'FAIL', '稻田面积占比',
              '%.1f%%（%.0f ha）；目标 %.1f%%' % (share, rice_a, PADDY_SHARE),
              '补充4：ESA 耕地拆分为水田 53.7% + 旱地 5.8%')
        top = ', '.join('%s %.1f%%' % (k, 100 * v / tot) for k, v in
                        sorted(agg.items(), key=lambda x: -x[1])[:6])
        R.add('INFO', '土地利用构成', top)

    # rice rotation
    rot = parse_mgt(d)
    rice_rots = {}
    for k, (pc, mg) in lum.items():
        if mg in rot and any('rice' in x[3].lower() for x in rot[mg]):
            rice_rots[mg] = rot[mg]
    for mg, ops in rice_rots.items():
        plnt = [(m, dd) for op, m, dd, c in ops if op == 'plnt' and 'rice' in c.lower()]
        dtbl = [c for op, m, dd, c in ops if op == 'auto']
        sched = '; '.join('%s %d/%d %s' % (op, m, dd, c) for op, m, dd, c in ops if op != 'auto')
        single = len(plnt) == 1
        R.add('PASS' if single else 'FAIL', '稻作制度 (%s)' % mg,
              '%s季稻 | %s' % ('单' if single else ('双' if len(plnt) == 2 else str(len(plnt))), sched),
              '补充4：改为单季中稻 5/15–9/30，冬季麦/油不淹灌')
        dbl = [x for x in dtbl if 'double' in x.lower()]
        if dbl:
            R.add('WARN', '决策表命名', '仍引用 %s' % ', '.join(dbl),
                  '名称含 double，确认淹灌窗口已改为仅中稻季')
    summary['rice_single'] = all(
        len([1 for op, m, dd, c in ops if op == 'plnt' and 'rice' in c.lower()]) == 1
        for ops in rice_rots.values()) if rice_rots else None

    # print settings
    pp = lines(d, 'print.prt', 2) or []
    flags = {t[0]: t[1:5] for t in pp if len(t) >= 5}
    if flags:
        wa = flags.get('water_allo', ['?'] * 4)
        cs = flags.get('channel_sd', ['?'] * 4)
        R.add('PASS' if cs[2] == 'y' else 'WARN', 'channel_sd 年输出', 'd/m/y/a = %s' % '/'.join(cs),
              'Result 3 的 δi 需要逐通道年均流量')
        R.add('PASS' if wa[1] == 'n' else 'WARN', 'water_allo 月输出', 'd/m/y/a = %s' % '/'.join(wa),
              '月输出 158 MB/情景，年输出即可')

    # big files already present
    big = [(fn, os.path.getsize(os.path.join(d, fn)) / 1e9) for fn in BIG_OUTPUTS
           if os.path.exists(os.path.join(d, fn))]
    if big:
        R.add('WARN', '大文件未清理', ', '.join('%s %.2f GB' % b for b in big),
              '跑完先生成汇总 CSV，再删除这些文件')

    summary['md5'] = {fn: md5(d, fn) for fn in PARAM_FILES}
    return R, summary


def check_cross(summ):
    R = Report('跨情景不变量（%d 个目录）' % len(summ))
    with_res = {k: s for k, s in summ.items() if s.get('n_res')}
    vols = {k: s['vol'] for k, s in with_res.items()}
    if len(vols) >= 2:
        spread = max(vols.values()) - min(vols.values())
        R.add('PASS' if spread < 1.0 else 'FAIL', '总库容守恒',
              '; '.join('%s=%.2f' % (os.path.basename(os.path.dirname(k)) or k, v) for k, v in vols.items()),
              '各聚合档 Σvol_ps 必须相等')
    fs = {k: s['f'] for k, s in with_res.items() if 'f' in s}
    if len(fs) >= 2:
        spread = max(fs.values()) - min(fs.values())
        R.add('PASS' if spread < 0.002 else 'FAIL', '拦截总量守恒',
              '; '.join('%s=%.4f' % (os.path.basename(os.path.dirname(k)) or k, v) for k, v in fs.items()),
              'f_i 由塘坝物理位置确定，各聚合档面积加权 f 必须相等')
    for fn in PARAM_FILES:
        hs = {k: s['md5'].get(fn) for k, s in summ.items() if s['md5'].get(fn)}
        if len(hs) >= 2:
            same = len(set(hs.values())) == 1
            R.add('PASS' if same else 'WARN', '参数一致: ' + fn,
                  '一致' if same else '不一致 (%d 种)' % len(set(hs.values())),
                  '实验 A 要求各情景参数相同；A2 重新划分流域时此项必然不同，需在文中说明')
    rs = {k: s.get('rice_share') for k, s in summ.items() if s.get('rice_share') is not None}
    if len(rs) >= 2:
        spread = max(rs.values()) - min(rs.values())
        R.add('PASS' if spread < 0.5 else 'WARN', '稻田面积一致',
              '; '.join('%.1f%%' % v for v in rs.values()),
              '各情景稻田面积应相同（A2 重新划分后允许小幅差异）')
    return R


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    total_fail, summ = 0, {}
    for d in argv:
        if not os.path.isdir(d):
            print('跳过（不是目录）:', d)
            continue
        R, s = check_folder(d)
        R.show()
        total_fail += R.fails()
        summ[d] = s
    if len(summ) >= 2:
        C = check_cross(summ)
        C.show()
        total_fail += C.fails()
    print('\n' + ('全部通过，可以开跑。' if total_fail == 0 else
                  '有 %d 项 FAIL —— 先修正再跑，避免返工。' % total_fail))
    return 1 if total_fail else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
