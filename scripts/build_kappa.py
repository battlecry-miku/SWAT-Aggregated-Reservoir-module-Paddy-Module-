# -*- coding: utf-8 -*-
"""Rewrite the hillslope-to-pond routing fractions of a configuration for a given kappa.

    python build_kappa.py <src TxtInOut> <dst TxtInOut> <kappa>
    python build_kappa.py --check <TxtInOut> <kappa>     # compare, write nothing

f_i = min(1, kappa * A_res,i / A_rtu,i)   (methods eq 18); A_res,i is the OFR water surface of the
routing unit from the verified centroid mapping, A_rtu,i the unit area from rout_unit.con.
The reservoir branch gets f_i and the channel branch 1 - f_i; other branches are untouched.
"""
import sys, io, os, shutil
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
MEMBER = os.path.join(HERE, 'swat_real_rerun_20260830', 'powerlaw_prior_20260911', 'ofr_membership.csv')


def pond_area_by_gis():
    m = pd.read_csv(MEMBER)
    return m.groupby(m.LSUID.astype(int)).area_ha.sum().to_dict()


def rewrite(src, dst, kappa, check=False):
    pa = pond_area_by_gis()
    L = open(os.path.join(src, 'rout_unit.con')).read().splitlines()
    tot_a = tot_fa = 0.0
    old_fa = 0.0
    out = list(L)
    n = 0
    for i in range(2, len(L)):
        t = L[i].split()
        if 'res' not in t:
            continue
        gis, area = int(t[2]), float(t[3])
        f = min(1.0, kappa * pa.get(gis, 0.0) / area) if area > 0 else 0.0
        p, q = t.index('res'), t.index('sdc')
        old_fa += area * float(t[p + 3])
        tot_a += area
        tot_fa += area * f
        t[p + 3] = '%.5f' % f
        t[q + 3] = '%.5f' % (1.0 - f)
        out[i] = ' '.join(t)
        n += 1
    fw_new, fw_old = tot_fa / tot_a, old_fa / tot_a
    print('%d 个汇水单元：面积加权 f 由 %.4f 改为 %.4f（κ = %.4g）' % (n, fw_old, fw_new, kappa))
    if check:
        return fw_old, fw_new
    if os.path.abspath(src) != os.path.abspath(dst):
        os.makedirs(dst, exist_ok=True)
        SKIP = lambda f: f.endswith(('_day.txt', '_mon.txt', '_yr.txt', '_aa.txt', '.log', '.out')) \
            or f.startswith('fort.') or f in ('taoxi_sim_daily.txt', 'success.fin')
        for f in os.listdir(src):
            if not SKIP(f) and os.path.isfile(os.path.join(src, f)):
                shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
    open(os.path.join(dst, 'rout_unit.con'), 'w').write('\n'.join(out) + '\n')
    return fw_old, fw_new


if __name__ == '__main__':
    if sys.argv[1] == '--check':
        rewrite(sys.argv[2], sys.argv[2], float(sys.argv[3]), check=True)
    else:
        rewrite(sys.argv[1], sys.argv[2], float(sys.argv[3]))
