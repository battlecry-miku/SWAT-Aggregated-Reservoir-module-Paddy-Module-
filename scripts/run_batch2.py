# -*- coding: utf-8 -*-
"""Batch 2 (experiment A): run A0-A4 with one set of calibrated parameters.

    python run_batch2.py --params <best.json> --out <dir> [--scales A0 A1 A2 A3 A4]
                         [--workers 5] [--end 2023] [--tag cal]

For every scale: copy the base configuration into <out>/<S>/native_runs/<S>_<tag>/TxtInOut,
write the calibrated parameters (same writer as dds_calibrate.py, so the 18 parameters land
identically in every scale), use the pinned exe, run, then
    summarize_run.py  (that scale's transfer metadata)  -> <out>/<S>/tables
    postrun_check.py  -> <out>/<S>/postrun.log
    eval_outlet.py    -> <out>/<S>/outlet.log
One result folder per scale because postrun_check reads every table in its folder.
A summary of all scales is written to <out>/batch2_summary.csv.
"""
import sys, io, os, re, json, shutil, argparse, subprocess, time
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dds_calibrate as D  # noqa: E402  (wraps stdout as UTF-8, line-buffered)

W = os.path.join(HERE, 'swat_real_rerun_20260830')
SC = os.path.join(W, 'result2_scales_20260911')
A4 = os.path.join(W, 'result2_areacap2_20260911')
EXE = os.path.join(HERE, 'bin', 'swatplus_rev62_pvolVc_25a71e76.exe')
BASE = {s: os.path.join(SC, '%s_base' % s, 'TxtInOut') for s in ('A0', 'A0ch', 'A1', 'A2', 'A3')}
BASE['A4'] = os.path.join(W, 'result2_powerlaw_20260911', 'A4_pl', 'TxtInOut')   # power-law capacity prior
META = {s: os.path.join(SC, 'scenario_meta', '%s_base_transfer_metadata.csv' % s) for s in BASE if s != 'A4'}
META['A4'] = os.path.join(A4, 'scenario_meta', 'A4_single_rice_supplyfix_validation_transfer_metadata.csv')
SKIP = lambda f: f.endswith(('_day.txt', '_mon.txt', '_yr.txt', '_aa.txt', '.log', '.out')) \
    or f.startswith('fort.') or f in ('taoxi_sim_daily.txt', 'success.fin')
PY = sys.executable


def prepare(scale, p, out, tag, end):
    rd = os.path.join(out, scale)
    txt = os.path.join(rd, 'native_runs', '%s_%s' % (scale, tag), 'TxtInOut')
    if os.path.exists(rd):
        shutil.rmtree(rd)
    os.makedirs(txt)
    src = BASE[scale]
    for f in os.listdir(src):
        if not SKIP(f) and os.path.isfile(os.path.join(src, f)):
            shutil.copy2(os.path.join(src, f), os.path.join(txt, f))
    shutil.copy2(EXE, os.path.join(txt, 'swatplus.exe'))
    D.write_params(src, txt, p)
    L = open(os.path.join(txt, 'time.sim')).read().splitlines()
    t = L[2].split(); t[3] = str(end)
    L[2] = '       %s      %s         %s      %s         %s  ' % tuple(t)
    open(os.path.join(txt, 'time.sim'), 'w').write('\n'.join(L) + '\n')
    return rd, txt


def run_one(scale, p, a):
    rd, txt = prepare(scale, p, a.out, a.tag, a.end)
    name = '%s_%s' % (scale, a.tag)
    t0 = time.time()
    with open(os.path.join(txt, 'run.log'), 'w') as so:
        rc = subprocess.run([os.path.join(txt, 'swatplus.exe')], cwd=txt, stdout=so,
                            stderr=subprocess.STDOUT).returncode
    ok = rc == 0 and os.path.exists(os.path.join(txt, 'success.fin'))
    print('[%s] SWAT+ rc=%d %s (%.0f s)' % (scale, rc, 'ok' if ok else 'FAILED', time.time() - t0))
    if not ok:
        return scale, {'scale': scale, 'run_ok': False}

    def py(args, log):
        with open(os.path.join(rd, log), 'w', encoding='utf-8') as f:
            return subprocess.run([PY] + args, cwd=HERE, stdout=f, stderr=subprocess.STDOUT,
                                  env=dict(os.environ, PYTHONIOENCODING='utf-8')).returncode

    rs = py(['summarize_run.py', rd, name, '--meta', META[scale],
             '--start-year', str(a.years[0]), '--end-year', str(a.years[1])], 'summarize.log')
    rp = py(['postrun_check.py', rd, '--years', str(a.years[0]), str(a.years[1])], 'postrun.log')
    ro = py(['eval_outlet.py', txt], 'outlet.log')
    res = {'scale': scale, 'run_ok': True, 'summarize_rc': rs, 'postrun_rc': rp, 'outlet_rc': ro}
    res.update(parse_logs(rd))
    print('[%s] summarize rc=%d  postrun rc=%d  outlet rc=%d' % (scale, rs, rp, ro))
    return scale, res


NUM = r'(-?\d+(?:\.\d+)?)'


def parse_logs(rd):
    """Pull the headline numbers out of the check logs (best effort; logs stay on disk)."""
    r = {}
    try:
        t = open(os.path.join(rd, 'postrun.log'), encoding='utf-8').read()
        r['postrun_FAIL'] = t.count('[FAIL]')
        r['postrun_WARN'] = t.count('[WARN]')
    except OSError:
        pass
    try:
        # eval_outlet prints a table: "<label> <years>  n  NSE  logNSE  KGE  PBIAS%  R2"
        for line in open(os.path.join(rd, 'outlet.log'), encoding='utf-8'):
            for lab, key in (('率定期', 'cal'), ('验证期', 'val')):
                if line.strip().startswith(lab):
                    nums = re.findall(NUM, line.split(None, 2)[-1] if len(line.split()) > 2 else '')
                    if len(nums) >= 6:
                        for c, v in zip(('n', 'NSE', 'logNSE', 'KGE', 'PBIAS', 'R2', 'logNSE1p'), nums[:7]):
                            r['%s_%s' % (key, c)] = float(v)
    except OSError:
        pass
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--params', required=True, help='best.json from dds_calibrate (uses its "params")')
    ap.add_argument('--out', required=True)
    ap.add_argument('--scales', nargs='+', default=['A0', 'A1', 'A2', 'A3', 'A4'])
    ap.add_argument('--workers', type=int, default=5)
    ap.add_argument('--end', type=int, default=2023)
    ap.add_argument('--years', type=int, nargs=2, default=(1985, 2023))
    ap.add_argument('--tag', default='cal')
    ap.add_argument('--base-root', help='take every scale from <dir>/<S>_base/TxtInOut instead of the defaults')
    ap.add_argument('--meta-root', help='transfer metadata dir (default: <base-root>/scenario_meta, else the defaults)')
    a = ap.parse_args()
    if a.base_root:
        for s in a.scales:
            BASE[s] = os.path.join(a.base_root, '%s_base' % s, 'TxtInOut')
        mr = a.meta_root or os.path.join(a.base_root, 'scenario_meta')
        for s in a.scales:
            p = os.path.join(mr, '%s_base_transfer_metadata.csv' % s)
            if os.path.exists(p):
                META[s] = p
    os.makedirs(a.out, exist_ok=True)
    bj = json.load(open(a.params, encoding='utf-8'))
    p = dict(D.base_values(BASE['A4']))
    p.update(bj['params'])
    missing = [s[0] for s in D.LAYER1 + D.LAYER2 if s[0] not in p]
    if missing:
        raise SystemExit('参数缺失: %s' % missing)
    json.dump({'source': os.path.abspath(a.params), 'params': p}, open(os.path.join(a.out, 'params_used.json'), 'w',
              encoding='utf-8'), indent=1, ensure_ascii=False)
    print('参数来源 %s；%d 个档：%s；并行 %d' % (a.params, len(a.scales), ' '.join(a.scales), a.workers))
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        res = dict(f.result() for f in [ex.submit(run_one, s, p, a) for s in a.scales])
    df = pd.DataFrame([res[s] for s in a.scales])
    df.to_csv(os.path.join(a.out, 'batch2_summary.csv'), index=False, encoding='utf-8-sig')
    print(df.to_string(index=False))


if __name__ == '__main__':
    main()
