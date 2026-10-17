# -*- coding: utf-8 -*-
"""Result-2 matrix: one factor at a time crossed with the aggregation scales (methods table 8).

    python run_matrix.py --params <best.json> --factor n|kappa|petco --levels 0.2 0.5 1.0 1.5
                         --out <dir> [--scales A1 A2 A3 A4] [--workers 4] [--base-root <dir>]

n      -> ofr_curve.par (retention curve exponent), config change, one base-root per level
kappa  -> rout_unit.con hillslope fractions via build_kappa.py, one base-root per level
petco  -> multiplier on the calibrated pet_co, a parameter change only (no config build)

Each level is run with run_batch2.py, so every cell gets the same summaries and checks.
Results land in <out>/<factor><level>/ ; a summary of all cells is written to <out>/matrix_summary.csv.
"""
import sys, os, json, glob, shutil, argparse, subprocess
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dds_calibrate as D  # noqa: E402  (wraps stdout)

W = os.path.join(HERE, 'swat_real_rerun_20260830')
DEFAULT_BASE = os.path.join(W, 'result2_scales_20260911')
A4_BASE = os.path.join(W, 'result2_powerlaw_20260911', 'A4_pl', 'TxtInOut')
META_DIR = os.path.join(DEFAULT_BASE, 'scenario_meta')
A4_META = os.path.join(W, 'result2_areacap2_20260911', 'scenario_meta',
                       'A4_single_rice_supplyfix_validation_transfer_metadata.csv')
SKIP = lambda f: f.endswith(('_day.txt', '_mon.txt', '_yr.txt', '_aa.txt', '.log', '.out')) \
    or f.startswith('fort.') or f in ('taoxi_sim_daily.txt', 'success.fin')


def base_dir(scale, base_root):
    if base_root:
        return os.path.join(base_root, '%s_base' % scale, 'TxtInOut')
    return A4_BASE if scale == 'A4' else os.path.join(DEFAULT_BASE, '%s_base' % scale, 'TxtInOut')


def copy_base(src, dst):
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        if not SKIP(f) and os.path.isfile(os.path.join(src, f)):
            shutil.copy2(os.path.join(src, f), os.path.join(dst, f))


def build_level(factor, level, scales, out_root, base_root):
    """Return (base_root_for_run, params_override) for one factor level."""
    if factor == 'petco':
        return None, level                      # parameter only
    root = os.path.join(out_root, '_cfg_%s%g' % (factor, level))
    os.makedirs(os.path.join(root, 'scenario_meta'), exist_ok=True)
    for s in scales:
        src, dst = base_dir(s, base_root), os.path.join(root, '%s_base' % s, 'TxtInOut')
        if factor == 'n':
            copy_base(src, dst)
            open(os.path.join(dst, 'ofr_curve.par'), 'w').write('n_ret %f\n' % level)
        elif factor == 'kappa':
            subprocess.run([sys.executable, os.path.join(HERE, 'build_kappa.py'), src, dst, str(level)],
                           check=True, env=dict(os.environ, PYTHONIOENCODING='utf-8'),
                           stdout=subprocess.DEVNULL)
        m = os.path.join(META_DIR, '%s_base_transfer_metadata.csv' % s)
        if s == 'A4':
            shutil.copy2(A4_META, os.path.join(root, 'scenario_meta', 'A4_base_transfer_metadata.csv'))
        elif os.path.exists(m):
            shutil.copy2(m, os.path.join(root, 'scenario_meta', os.path.basename(m)))
    return root, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--params', required=True)
    ap.add_argument('--factor', required=True, choices=['n', 'kappa', 'petco'])
    ap.add_argument('--levels', nargs='+', type=float, required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--scales', nargs='+', default=['A1', 'A2', 'A3', 'A4'])
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--base-root', default=None)
    ap.add_argument('--years', type=int, nargs=2, default=(1985, 2023))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows = []
    for lev in a.levels:
        cfg, pet = build_level(a.factor, lev, a.scales, a.out, a.base_root)
        params = a.params
        if a.factor == 'petco':
            b = json.load(open(a.params, encoding='utf-8'))
            p = dict(b['params'])
            p['petco'] = p['petco'] * lev
            params = os.path.join(a.out, '_params_petco%g.json' % lev)
            json.dump({'params': p, 'note': 'calibrated petco x %g' % lev}, open(params, 'w'), indent=1)
        cell = os.path.join(a.out, '%s%g' % (a.factor, lev))
        cmd = [sys.executable, os.path.join(HERE, 'run_batch2.py'), '--params', params, '--out', cell,
               '--scales'] + a.scales + ['--workers', str(a.workers), '--tag', '%s%g' % (a.factor, lev),
                                         '--years', str(a.years[0]), str(a.years[1])]
        if cfg:
            cmd += ['--base-root', cfg]
        print('\n=== %s = %g ===' % (a.factor, lev), flush=True)
        subprocess.run(cmd, check=True, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        f = os.path.join(cell, 'batch2_summary.csv')
        if os.path.exists(f):
            d = pd.read_csv(f, encoding='utf-8-sig')
            d.insert(0, a.factor, lev)
            rows.append(d)
    if rows:
        out = pd.concat(rows, ignore_index=True)
        out.to_csv(os.path.join(a.out, 'matrix_summary.csv'), index=False, encoding='utf-8-sig')
        print('\n矩阵汇总:')
        print(out.to_string(index=False))


if __name__ == '__main__':
    main()
