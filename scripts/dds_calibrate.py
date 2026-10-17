# -*- coding: utf-8 -*-
"""Multi-start DDS calibration of the SWAT+ A4 baseline by direct input edits.

Layer 1: 12 hydrology / soil parameters (Table 4 of the manuscript).
Layer 2: 6 channel parameters grouped by Strahler order (Table 5), applied on
         top of the best layer-1 solution.

    python dds_calibrate.py --base <TxtInOut> --out <dir> --layer 1
        [--chains 10] [--iters 60] [--workers 10] [--end 2016]
        [--eval 1985 2016] [--fixed best_layer1.json] [--seed 1]

Each chain runs sequentially in its own worker copy of <base>; chains run in
parallel.  Only the outlet file is read; every other output is deleted after
each evaluation.  Results: <out>/chain_<k>.csv and <out>/best.json.
"""
import sys, io, os, csv, json, math, time, shutil, random, argparse, subprocess, datetime, threading
from concurrent.futures import ThreadPoolExecutor
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
OBS = os.path.join(HERE, 'swat_real_rerun_20260830', 'scale_conclusion_fdc_20260904',
                   'scale_conclusion_daily_flow_matrix_s0_s1_s2_s3cap500.csv')

# name, kind ('rel' multiplies base, 'abs' replaces), lo, hi
LAYER1 = [('cn2', 'rel', -0.15, 0.35), ('awc', 'rel', -0.50, 0.30), ('k', 'rel', -0.75, 0.75),
          ('esco', 'abs', 0.30, 1.00), ('epco', 'abs', 0.40, 1.00), ('perco', 'abs', 0.05, 1.00),
          ('latq_co', 'abs', 0.00, 1.00), ('cn3_swf', 'abs', 0.00, 1.00), ('petco', 'abs', 0.80, 1.20),
          ('alpha', 'abs', 0.005, 0.30), ('deep_seep', 'abs', 0.001, 0.35), ('surlag', 'abs', 0.05, 12.0)]
LAYER2 = [('mann_ord12', 'abs', 0.045, 0.09), ('mann_ord34', 'abs', 0.045, 0.09),
          ('slp_mult_ord12', 'abs', 0.7, 6.0), ('slp_mult_ord34', 'abs', 0.7, 6.0),
          ('len_mult_ord12', 'abs', 0.5, 1.3), ('len_mult_ord34', 'abs', 0.5, 1.3)]
PARAM_FILES = ['cntable.lum', 'soils.sol', 'hydrology.hyd', 'aquifer.aqu', 'parameters.bsn', 'hyd-sed-lte.cha']
KEEP_OUT = {'taoxi_sim_daily.txt'}
OBJECTIVE, LAMBDA = 'lognse', 0.0      # set from --obj / --lam in main()


# ------------------------------------------------------------------ observations
def read_obs():
    o = {}
    with open(OBS, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            try:
                d = datetime.date.fromisoformat(r['date'])
                v = float(r['obs_m3s'])
            except (ValueError, KeyError):
                continue
            if v > 0:
                o[(d.year, d.timetuple().tm_yday)] = v
    return o


def metrics(txt, obs, y0, y1):
    sim = {}
    with open(os.path.join(txt, 'taoxi_sim_daily.txt'), errors='ignore') as f:
        f.readline()
        for L in f:
            t = L.split()
            if len(t) > 6:
                try:
                    sim[(int(t[3]), int(t[0]))] = float(t[6]) / 86400.0
                except ValueError:
                    pass
    k = [x for x in obs if y0 <= x[0] <= y1 and x in sim]
    o = np.array([obs[x] for x in k]); s = np.array([sim[x] for x in k])
    lo, ls = np.log(o), np.log(np.maximum(s, 1e-3))
    lnse = 1 - np.sum((ls - lo) ** 2) / np.sum((lo - lo.mean()) ** 2)
    nse = 1 - np.sum((s - o) ** 2) / np.sum((o - o.mean()) ** 2)
    r = np.corrcoef(o, s)[0, 1]
    kge = 1 - math.sqrt((r - 1) ** 2 + (s.std() / o.std() - 1) ** 2 + (s.mean() / o.mean() - 1) ** 2)
    pbias = 100 * np.sum(o - s) / np.sum(o)
    # FDC shape: log10 RMSE between simulated and observed mean annual FDCs (1-99 %), matched days
    yrs = np.array([x[0] for x in k]); pg = np.linspace(1.0, 99.0, 981)

    def fdc(v):
        v = np.sort(v)[::-1]
        return np.interp(pg, np.arange(1, len(v) + 1) / (len(v) + 1.0) * 100, v)
    ys = [y for y in np.unique(yrs) if (yrs == y).sum() >= 250]
    fo = np.mean([fdc(o[yrs == y]) for y in ys], axis=0)
    fs = np.mean([fdc(np.maximum(s[yrs == y], 1e-3)) for y in ys], axis=0)
    fdc_rmse = float(np.sqrt(np.mean((np.log10(fs) - np.log10(fo)) ** 2)))
    obj = lnse - LAMBDA * fdc_rmse if OBJECTIVE == 'lognse_fdc' else lnse
    return dict(logNSE=lnse, NSE=nse, KGE=kge, PBIAS=pbias, FDC=fdc_rmse, obj=obj, n=len(k))


# ------------------------------------------------------------------ parameter writers
def base_values(base):
    """Current values of the absolute-type parameters (used as the chain-1 start)."""
    L = open(os.path.join(base, 'hydrology.hyd')).read().splitlines()
    h = L[1].split(); r = L[2].split()
    v = {k: float(r[h.index(c)]) for k, c in
         [('esco', 'esco'), ('epco', 'epco'), ('perco', 'perco'), ('latq_co', 'latq_co'),
          ('cn3_swf', 'cn3_swf'), ('petco', 'pet_co')]}
    A = open(os.path.join(base, 'aquifer.aqu')).read().splitlines()
    h = A[1].split(); r = A[2].split()
    v['alpha'] = float(r[h.index('alpha_bf')]); v['deep_seep'] = float(r[h.index('rchg_dp')])
    B = open(os.path.join(base, 'parameters.bsn')).read().splitlines()
    v['surlag'] = float(B[2].split()[B[1].split().index('surq_lag')])
    for k in ('cn2', 'awc', 'k'):
        v[k] = 0.0
    C = open(os.path.join(base, 'hyd-sed-lte.cha')).read().splitlines()
    h = C[1].split(); im, io_ = h.index('mann'), h.index('order')
    m12 = [float(l.split()[im]) for l in C[2:] if l.split() and int(l.split()[io_]) <= 2]
    m34 = [float(l.split()[im]) for l in C[2:] if l.split() and int(l.split()[io_]) >= 3]
    v.update(mann_ord12=float(np.mean(m12)), mann_ord34=float(np.mean(m34)),
             slp_mult_ord12=1.0, slp_mult_ord34=1.0, len_mult_ord12=1.0, len_mult_ord34=1.0)
    return v


def write_params(base_txt, work, p):
    """Rewrite the parameter files in <work> from the pristine copies in <base_txt>."""
    rd = lambda f: open(os.path.join(base_txt, f)).read().splitlines()
    wr = lambda f, L: open(os.path.join(work, f), 'w').write('\n'.join(L) + '\n')
    # curve numbers
    L = rd('cntable.lum')
    for i in range(2, len(L)):
        t = L[i].split()
        if len(t) >= 5:
            try:
                cn = [min(98.0, max(30.0, float(x) * (1 + p['cn2']))) for x in t[1:5]]
            except ValueError:
                continue
            L[i] = '%-20s' % t[0] + ''.join('%14.5f' % x for x in cn) + '  ' + ' '.join(t[5:])
    wr('cntable.lum', L)
    # soils: layer lines have 14 numeric fields; awc at 2, soil_k at 3
    L = rd('soils.sol')
    for i in range(2, len(L)):
        t = L[i].split()
        if len(t) == 14:
            try:
                vals = [float(x) for x in t]
            except ValueError:
                continue
            vals[2] = min(1.0, max(0.01, vals[2] * (1 + p['awc'])))
            vals[3] = max(1e-4, vals[3] * (1 + p['k']))
            L[i] = ' '.join('%.5f' % x for x in vals)
    wr('soils.sol', L)
    # HRU hydrology
    L = rd('hydrology.hyd'); h = L[1].split()
    cols = {'esco': 'esco', 'epco': 'epco', 'perco': 'perco', 'latq_co': 'latq_co',
            'cn3_swf': 'cn3_swf', 'petco': 'pet_co'}
    for i in range(2, len(L)):
        t = L[i].split()
        if len(t) == len(h):
            for k, c in cols.items():
                t[h.index(c)] = '%.5f' % p[k]
            L[i] = ' '.join(t)
    wr('hydrology.hyd', L)
    # aquifers
    L = rd('aquifer.aqu'); h = L[1].split()
    for i in range(2, len(L)):
        t = L[i].split()
        if len(t) == len(h):
            t[h.index('alpha_bf')] = '%.5f' % p['alpha']
            t[h.index('rchg_dp')] = '%.5f' % p['deep_seep']
            L[i] = ' '.join(t)
    wr('aquifer.aqu', L)
    # basin surface lag
    L = rd('parameters.bsn'); h = L[1].split(); t = L[2].split()
    t[h.index('surq_lag')] = '%.5f' % p['surlag']; L[2] = ' '.join(t)
    wr('parameters.bsn', L)
    # channels by Strahler order
    L = rd('hyd-sed-lte.cha'); h = L[1].split()
    im, io_, isl, il = h.index('mann'), h.index('order'), h.index('slp'), h.index('len')
    for i in range(2, len(L)):
        t = L[i].split()
        if len(t) >= len(h) - 2 and t[io_].lstrip('-').isdigit():
            g = '12' if int(t[io_]) <= 2 else '34'
            t[im] = '%.5f' % p['mann_ord' + g]
            t[isl] = '%.6f' % (float(t[isl]) * p['slp_mult_ord' + g])
            t[il] = '%.6f' % (float(t[il]) * p['len_mult_ord' + g])
            L[i] = ' '.join(t)
    wr('hyd-sed-lte.cha', L)


def prepare_worker(base, work, end_year):
    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work)
    for f in os.listdir(base):
        if f.endswith(('_day.txt', '_mon.txt', '_yr.txt', '_aa.txt', '.log')) or f.startswith('fort.') \
                or f in ('taoxi_sim_daily.txt', 'simulation.out', 'success.fin'):
            continue
        s = os.path.join(base, f)
        (shutil.copytree if os.path.isdir(s) else shutil.copy2)(s, os.path.join(work, f))
    L = open(os.path.join(work, 'time.sim')).read().splitlines(); t = L[2].split(); t[3] = str(end_year)
    L[2] = '       %s      %s         %s      %s         %s  ' % tuple(t)
    open(os.path.join(work, 'time.sim'), 'w').write('\n'.join(L) + '\n')
    o = []
    for l in open(os.path.join(work, 'print.prt')).read().splitlines():
        t = l.split()
        if t and len(t) == 5 and t[1] in 'yn' and t[2] in 'yn' and t[3] in 'yn' and t[4] in 'yn':
            l = '%-24s %13s %13s %13s %13s' % (t[0], 'n', 'n', 'n', 'n')
        o.append(l)
    open(os.path.join(work, 'print.prt'), 'w').write('\n'.join(o) + '\n')


def clean_outputs(work):
    for f in os.listdir(work):
        if (f.endswith(('_day.txt', '_mon.txt', '_yr.txt', '_aa.txt')) or f.startswith('fort.')) \
                and f not in KEEP_OUT:
            try:
                os.remove(os.path.join(work, f))
            except OSError:
                pass


# ------------------------------------------------------------------ DDS
def run_chain(k, args, space, fixed, x0, obs, base):
    rng = random.Random(args.seed * 1000 + k)
    work = os.path.join(args.out, 'work_%02d' % k)
    prepare_worker(base, work, args.end)
    log = os.path.join(args.out, 'chain_%02d.csv' % k)
    names = [s[0] for s in space]
    lo = np.array([s[2] for s in space]); hi = np.array([s[3] for s in space])

    def evaluate(x):
        p = dict(fixed); p.update(dict(zip(names, x)))
        write_params(base, work, p)
        for f in ('taoxi_sim_daily.txt', 'success.fin'):
            if os.path.exists(os.path.join(work, f)):
                os.remove(os.path.join(work, f))
        t0 = time.time()
        with open(os.path.join(work, 'run.log'), 'w') as so:
            rc = subprocess.run([os.path.join(work, 'swatplus.exe')], cwd=work, stdout=so,
                                stderr=subprocess.STDOUT, timeout=3600).returncode
        ok = rc == 0 and os.path.exists(os.path.join(work, 'success.fin'))
        m = metrics(work, obs, *args.eval) if ok else dict(logNSE=-9e9, NSE=np.nan, KGE=np.nan, PBIAS=np.nan, FDC=np.nan, obj=-9e9, n=0)
        clean_outputs(work)
        return m, time.time() - t0

    def propose(it, best_x):
        pr = 1 - math.log(it) / math.log(args.iters)
        sel = [j for j in range(len(best_x)) if rng.random() < pr] or [rng.randrange(len(best_x))]
        cand = best_x.copy()
        for j in sel:
            v = cand[j] + 0.2 * (hi[j] - lo[j]) * rng.gauss(0, 1)
            if v < lo[j]:
                v = lo[j] + (lo[j] - v); v = hi[j] if v > hi[j] else v
            if v > hi[j]:
                v = hi[j] - (v - hi[j]); v = lo[j] if v < lo[j] else v
            cand[j] = v
        return cand

    x = np.array(x0 if k == 0 else [rng.uniform(a, b) for a, b in zip(lo, hi)])
    if args.init_from:
        # warm start: chain k begins at the best point of chain k of an earlier search
        # (the uniform draw above is still made so the random sequence stays reproducible)
        prev = os.path.join(args.init_from, 'chain_%02d.csv' % k)
        if os.path.exists(prev):
            with open(prev, newline='') as f:
                pr = [r for r in csv.DictReader(f) if r.get('logNSE') not in (None, '', 'nan')]
            if pr:
                key = 'obj' if pr[0].get('obj') not in (None, '') else 'logNSE'
                b = max(pr, key=lambda r: float(r[key]))
                x = np.array([min(h, max(l, float(b[n]))) for n, l, h in zip(names, lo, hi)])
    done = []
    if args.resume and os.path.exists(log):
        with open(log, newline='') as f:
            done = [r for r in csv.DictReader(f) if r.get('best_logNSE')]
    if done:
        # the random draws depend only on the iteration index, so replaying propose() puts the
        # generator back where the interrupted chain left it; best point is rebuilt from the log
        best_x, best_m = None, None
        for r in done:
            if int(r['iter']) > 0:
                propose(int(r['iter']), best_x)
            xr = np.array([float(r[n]) for n in names])
            mr = {c: float(r[c]) for c in ('logNSE', 'NSE', 'KGE', 'PBIAS', 'FDC', 'obj')}
            if best_m is None or mr['obj'] > best_m['obj']:
                best_x, best_m = xr, mr
        start = len(done)
        print('[chain %02d] resumed after iter %d  best %.4f' % (k, start - 1, best_m['obj']))
    else:
        m, dt = evaluate(x)
        best_x, best_m = x.copy(), m
        with open(log, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['iter'] + names + ['logNSE', 'NSE', 'KGE', 'PBIAS', 'FDC', 'obj', 'sec', 'best_logNSE'])
            w.writerow([0] + ['%.6g' % v for v in x] + ['%.4f' % m['logNSE'], '%.4f' % m['NSE'],
                       '%.4f' % m['KGE'], '%.2f' % m['PBIAS'], '%.4f' % m['FDC'], '%.4f' % m['obj'],
                       '%.0f' % dt, '%.4f' % best_m['obj']])
        print('[chain %02d] iter 0  obj %.4f  logNSE %.4f  FDC %.4f  KGE %.3f  PBIAS %.1f  (%.0fs)'
              % (k, m['obj'], m['logNSE'], m['FDC'], m['KGE'], m['PBIAS'], dt))
        start = 1
    for it in range(start, args.iters):
        cand = propose(it, best_x)
        m, dt = evaluate(cand)
        if m['obj'] > best_m['obj']:
            best_x, best_m = cand.copy(), m
        with open(log, 'a', newline='') as f:
            csv.writer(f).writerow([it] + ['%.6g' % v for v in cand] + ['%.4f' % m['logNSE'], '%.4f' % m['NSE'],
                                   '%.4f' % m['KGE'], '%.2f' % m['PBIAS'], '%.4f' % m['FDC'], '%.4f' % m['obj'],
                                   '%.0f' % dt, '%.4f' % best_m['obj']])
        print('[chain %02d] iter %d  obj %.4f  logNSE %.4f  FDC %.4f  best %.4f  (%.0fs)'
              % (k, it, m['obj'], m['logNSE'], m['FDC'], best_m['obj'], dt))
    return k, dict(zip(names, best_x.tolist())), best_m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--layer', type=int, default=1)
    ap.add_argument('--chains', type=int, default=10)
    ap.add_argument('--iters', type=int, default=60)
    ap.add_argument('--workers', type=int, default=10)
    ap.add_argument('--end', type=int, default=2016)
    ap.add_argument('--eval', type=int, nargs=2, default=(1985, 2016))
    ap.add_argument('--fixed', default=None, help='json of parameters held fixed (e.g. layer-1 best)')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--resume', action='store_true', help='continue chains from existing chain_*.csv')
    ap.add_argument('--init-from', default=None, help='warm start: chain k starts at the best point of <dir>/chain_k.csv')
    ap.add_argument('--obj', choices=('lognse', 'lognse_fdc'), default='lognse',
                    help='lognse_fdc: maximise logNSE - lam * FDC log10-RMSE (mean annual FDC, eval years)')
    ap.add_argument('--lam', type=float, default=5.0)
    args = ap.parse_args()
    global OBJECTIVE, LAMBDA
    OBJECTIVE, LAMBDA = args.obj, (args.lam if args.obj == 'lognse_fdc' else 0.0)
    os.makedirs(args.out, exist_ok=True)
    base = os.path.abspath(args.base)
    obs = read_obs()
    bv = base_values(base)
    fixed = dict(bv)
    if args.fixed:
        fixed.update(json.load(open(args.fixed, encoding='utf-8'))['params'])
    space = LAYER1 if args.layer == 1 else LAYER2
    x0 = [min(hi, max(lo, fixed[n])) for n, _, lo, hi in space]
    print('objective %s (lambda %.2f)' % (OBJECTIVE, LAMBDA))
    print('layer %d, %d params, %d chains x %d iters, %d workers, run to %d, eval %d-%d'
          % (args.layer, len(space), args.chains, args.iters, args.workers, args.end, *args.eval))
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_chain, k, args, space, fixed, x0, obs, base) for k in range(args.chains)]
        for f in futs:
            results.append(f.result())
    # search objective is logNSE (as in the manuscript); final selection additionally
    # requires |PBIAS| <= PBIAS_MAX over the calibration period, taken from every logged evaluation
    PBIAS_MAX = 10.0
    names = [s[0] for s in space]
    allrows = []
    for kk in range(args.chains):
        with open(os.path.join(args.out, 'chain_%02d.csv' % kk), newline='') as f:
            for r in csv.DictReader(f):
                r['chain'] = kk
                allrows.append(r)
    fl = lambda r, c: float(r[c]) if r[c] not in ('', 'nan') else float('nan')
    key = 'obj' if 'obj' in allrows[0] else 'logNSE'
    unc = max(allrows, key=lambda r: fl(r, key))
    ok = [r for r in allrows if abs(fl(r, 'PBIAS')) <= PBIAS_MAX]
    sel = max(ok, key=lambda r: fl(r, key)) if ok else unc

    def pack(r):
        p = dict(fixed); p.update({n: float(r[n]) for n in names})
        return {'chain': r['chain'], 'iter': int(r['iter']),
                'metrics': {c: fl(r, c) for c in ('logNSE', 'NSE', 'KGE', 'PBIAS', 'FDC', 'obj') if c in r},
                'params': p}
    out = {'layer': args.layer, 'objective': OBJECTIVE, 'lambda': LAMBDA, 'selection': '|PBIAS| <= %.0f%%' % PBIAS_MAX,
           'n_evaluations': len(allrows), 'n_within_pbias': len(ok),
           'selected': pack(sel), 'best_unconstrained': pack(unc)}
    out['params'] = out['selected']['params']          # consumed by --fixed for layer 2
    json.dump(out, open(os.path.join(args.out, 'best.json'), 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
    for lab, r in (('SELECTED (|PBIAS|<=%.0f%%)' % PBIAS_MAX, sel), ('UNCONSTRAINED', unc)):
        print('%-24s chain %s iter %s  obj %.4f  logNSE %.4f  KGE %.3f  PBIAS %.1f'
              % (lab, r['chain'], r['iter'], fl(r, key), fl(r, 'logNSE'), fl(r, 'KGE'), fl(r, 'PBIAS')))
    for d in os.listdir(args.out):
        if d.startswith('work_'):
            shutil.rmtree(os.path.join(args.out, d), ignore_errors=True)


if __name__ == '__main__':
    main()
