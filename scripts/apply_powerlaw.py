# -*- coding: utf-8 -*-
"""Area-volume power-law capacity prior (methods 2.2.1, eqs 15-17) for the aggregated OFR objects.

    python apply_powerlaw.py table [--b 1.4367]                 -> capacity tables (csv) for A1-A4
    python apply_powerlaw.py write <TxtInOut> <A1|A2|A3|A4> [--b 1.4367]
                                                                  -> rewrite hydrology.res in place

V_j = c * A_j^b for every one of the 4298 ponds, c = V_total / sum_j A_j^b, so the basin total
V_total = 5650.36 ha-m (56.50 Mm3) is unchanged; Vc,i = sum of V_j over the members of object i.
Only vol_ps / vol_es change: water-surface areas stay as they are, and vol_es keeps the SWAT+
editor ratio vol_es = 1.3225 * vol_ps already used by every configuration.

Pond membership: pond centroid (ESA WorldCover class-80 inventory, 4298 small water bodies)
-> original QSWAT+ LSU (lsus1.shp, LSUID = rout_unit.con gis_id) -> A4 object via rout_unit.con;
-> LSU subbasin -> A3 object res_sbNNN; -> A2 zone via the S7_merged24 group map; A1 = all.
Checked: per-object pond area reproduces hydrology.res area_ps for 163/165 A4 objects within
0.05 ha (max 0.36 ha); 3 centroids outside every LSU polygon go to the nearest LSU.
"""
import sys, io, os, argparse
import numpy as np, pandas as pd, geopandas as gpd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, 'swat_real_rerun_20260830')
GPKG = os.path.join(W, 's7_aggregation_20260909', 'S7_rebuilt_QSWAT_project', 'Watershed', 'Derived_Taoxi_Only',
                    'taoxi_upstream_pond_rice_layers.gpkg')
LSU = os.environ.get('SWAT_OFR_LSU', os.path.join(HERE, 'private_inputs', 'lsus.shp'))
A4 = os.path.join(W, 'result2_areacap2_20260911', 'native_runs', 'A4_single_rice_areacap', 'TxtInOut')
A3 = os.path.join(W, 'result2_formal_20260910', 'native_runs', 'A3_BASE', 'TxtInOut')
A2_GROUPS = os.path.join(W, 's7_aggregation_20260909', 'tables', 'S7_merged24_aggregated_reservoir_properties.csv')
OUT = os.path.join(W, 'powerlaw_prior_20260911')
V_TOTAL_HAM = 5650.36
ES_RATIO = 1.3225
B_DEFAULT = 1.4367


def ponds():
    ce = gpd.read_file(GPKG, layer='taoxi_small_pond_centroids')
    ce = ce[ce['class'] == 'small_waterbody_candidate'].copy()
    ls = gpd.read_file(LSU)[['LSUID', 'Subbasin', 'geometry']]
    j = gpd.sjoin(ce[['wb_id', 'area_ha', 'geometry']].to_crs(ls.crs), ls, how='left', predicate='within')
    j = j[~j.index.duplicated()]
    miss = j.LSUID.isna()
    if miss.any():
        nn = gpd.sjoin_nearest(ce.loc[miss, ['wb_id', 'geometry']].to_crs(ls.crs), ls, how='left')
        nn = nn[~nn.index.duplicated()]
        j.loc[miss, 'LSUID'] = nn.LSUID.values
        j.loc[miss, 'Subbasin'] = nn.Subbasin.values
    j['LSUID'] = j.LSUID.astype(int)
    j['Subbasin'] = j.Subbasin.astype(int)
    # A4 object via routing units
    g2r = {}
    for l in open(os.path.join(A4, 'rout_unit.con')).readlines()[2:]:
        t = l.split()
        if 'res' in t:
            g2r[int(t[2])] = int(t[t.index('res') + 1])
    j['A4'] = j.LSUID.map(g2r)
    # A3 object via subbasin name res_sbNNN
    s2r = {}
    for l in open(os.path.join(A3, 'reservoir.con')).readlines()[2:]:
        t = l.split()
        if len(t) > 2 and t[1].startswith('res_sb'):
            s2r[int(t[1][6:])] = int(t[0])
    j['A3'] = j.Subbasin.map(s2r)
    g = pd.read_csv(A2_GROUPS, encoding='utf-8-sig')
    a3a2 = {int(o): int(r.res_id) for r in g.itertuples() for o in str(r.old_res_ids).split(';')}
    j['A2'] = j.A3.map(a3a2)
    j['A1'] = 1
    return pd.DataFrame(j.drop(columns=['geometry', 'index_right'], errors='ignore'))


def capacities(p, b):
    a = p.area_ha.values * 1e4                       # m2
    c = V_TOTAL_HAM / np.sum(a ** b)
    p = p.assign(V_ham=c * a ** b)
    out = {}
    for s in ('A1', 'A2', 'A3', 'A4'):
        q = p.dropna(subset=[s])
        grp = q.groupby(q[s].astype(int))
        out[s] = pd.DataFrame({'area_ha': grp.area_ha.sum(), 'n_ofr': grp.size(), 'vol_ps_ham': grp.V_ham.sum()})
    return out, c


def write(txt, scale, b):
    p = ponds()
    caps, _ = capacities(p, b)
    cap = caps[scale]
    con = {int(l.split()[0]): l.split()[1] for l in open(os.path.join(txt, 'reservoir.con')).readlines()[2:]
           if len(l.split()) > 2}
    byname = {con[i]: v for i, v in cap.vol_ps_ham.items() if i in con}
    L = open(os.path.join(txt, 'hydrology.res')).read().splitlines()
    hdr = L[1].split()
    ip, ie = hdr.index('vol_ps'), hdr.index('vol_es')
    n = 0
    for i in range(2, len(L)):
        t = L[i].split()
        if len(t) >= len(hdr) and t[0] in byname:
            t[ip] = '%.5f' % byname[t[0]]
            t[ie] = '%.5f' % (byname[t[0]] * ES_RATIO)
            L[i] = '%-16s' % t[0] + ' '.join('%s' % x for x in t[1:])
            n += 1
    L[0] = L[0] + ' | power-law prior b=%.4f (apply_powerlaw.py)' % b
    open(os.path.join(txt, 'hydrology.res'), 'w').write('\n'.join(L) + '\n')
    tot = sum(float(l.split()[ip]) for l in L[2:] if len(l.split()) >= len(hdr))
    print('%s: %d/%d 个对象改写，Σvol_ps = %.2f ha·m → %s' % (scale, n, len(con), tot, txt))
    if n != len(con):
        raise SystemExit('有塘坝对象未取得幂律库容')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['table', 'write'])
    ap.add_argument('txt', nargs='?')
    ap.add_argument('scale', nargs='?')
    ap.add_argument('--b', type=float, default=B_DEFAULT)
    a = ap.parse_args()
    if a.mode == 'write':
        write(a.txt, a.scale, a.b)
        return
    os.makedirs(OUT, exist_ok=True)
    p = ponds()
    p.to_csv(os.path.join(OUT, 'ofr_membership.csv'), index=False, encoding='utf-8-sig')
    print('塘坝 %d 座，Σ面积 %.2f ha；未连塘坝对象的塘坝 (A4) %d 座' % (len(p), p.area_ha.sum(), p.A4.isna().sum()))
    for b in (1.0, a.b):
        caps, c = capacities(p, b)
        for s, d in caps.items():
            d['depth_m'] = d.vol_ps_ham / d.area_ha
            d.to_csv(os.path.join(OUT, 'capacity_%s_b%.4f.csv' % (s, b)), encoding='utf-8-sig')
        print('b=%.4f: c=%.4g；各档 Σvol_ps: %s' % (b, c, {s: round(d.vol_ps_ham.sum(), 2) for s, d in caps.items()}))
    # model check: b=1 must reproduce the current constant-depth hydrology.res of A4
    hr = {l.split()[0]: float(l.split()[4]) for l in open(os.path.join(A4, 'hydrology.res')).readlines()[2:]
          if len(l.split()) >= 7}
    con = {int(l.split()[0]): l.split()[1] for l in open(os.path.join(A4, 'reservoir.con')).readlines()[2:]
           if len(l.split()) > 2}
    c1, _ = capacities(p, 1.0)
    d = pd.Series({i: c1['A4'].vol_ps_ham.get(i, 0) - hr[con[i]] for i in con})
    print('b=1 与现模型 A4 vol_ps 对比: 最大差 %.2f ha·m（面积差 0.36 ha × 2.73 m 以内即正确）' % d.abs().max())
    cp = capacities(p, a.b)[0]
    for s in ('A2', 'A3', 'A4'):
        r = cp[s].vol_ps_ham / c1[s].vol_ps_ham
        print('%s: 幂律/常数库深 库容比 中位 %.2f，范围 %.2f–%.2f（%d 个对象）' % (s, r.median(), r.min(), r.max(), len(r)))


if __name__ == '__main__':
    main()
