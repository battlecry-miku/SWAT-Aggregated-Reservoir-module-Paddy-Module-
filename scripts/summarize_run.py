# -*- coding: utf-8 -*-
"""Build the summary tables that postrun_check.py reads, then prune large outputs.

    python summarize_run.py <result_dir> <scenario_name> [--keep]

<result_dir>/native_runs/<scenario_name>/TxtInOut must hold a finished run with
daily `reservoir` and yearly `water_allo` output; <result_dir>/scenario_meta must
hold <meta_scenario>_transfer_metadata.csv (any name ending in that suffix).
Writes <result_dir>/tables/{scenario}_reservoir_year_summary.csv and
{scenario}_water_allocation_annual.csv; deletes the big daily files unless --keep.
"""
import sys, io, os, glob, importlib.util, argparse
from pathlib import Path
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = Path(__file__).resolve().parent
PARSER = HERE / 'swat_real_rerun_20260830' / 'result2_supply_fix_20260911' / 'run_supply_fix_a4_validation.py'
BIG = ['reservoir_day.txt', 'wetland_day.txt', 'water_allo_day.txt', 'water_allo_mon.txt',
       'hru_wb_day.txt', 'fort.100100']


def reservoir_summary(txt):
    pv, ev = {}, {}
    for L in open(txt / 'hydrology.res').readlines()[2:]:
        t = L.split()
        if len(t) >= 7:
            pv[t[0]] = float(t[4]) * 1e4
            ev[t[0]] = float(t[6]) * 1e4
    rows = []
    with open(txt / 'reservoir_day.txt', errors='ignore') as f:
        for _ in range(3):
            f.readline()
        for L in f:
            t = L.split()
            if len(t) >= 48:
                rows.append((int(t[3]), int(t[4]), t[6], float(t[8]), float(t[9]), float(t[10]),
                             float(t[11]), float(t[29]), float(t[47])))
    d = pd.DataFrame(rows, columns=['yr', 'unit', 'name', 'precip_m3', 'evap_m3', 'seep_m3',
                                    'stor', 'flo_in_m3', 'flo_out_m3'])
    # Vc = principal spillway volume: the level at which the ponds spill and at which the
    # retention curve reaches K = 0 (res_control uses pvol since 2026-09-12)
    d['Vc_m3'] = d.name.map(pv)
    d['Pvol_m3'] = d.name.map(pv)
    d['Evol_m3'] = d.name.map(ev)
    d['W_Vc'] = d.stor / d.Vc_m3
    g = d.groupby(['yr', 'unit', 'name'])
    out = g.agg(days=('stor', 'size'), sum_W_Vc=('W_Vc', 'sum'), max_W_Vc=('W_Vc', 'max'),
                days_W_Vc_ge_095=('W_Vc', lambda s: int((s >= 0.95).sum())),
                days_W_Vc_ge_100=('W_Vc', lambda s: int((s >= 1.0).sum())),
                precip_m3=('precip_m3', 'sum'), evap_m3=('evap_m3', 'sum'), seep_m3=('seep_m3', 'sum'),
                flo_in_m3=('flo_in_m3', 'sum'), flo_out_m3=('flo_out_m3', 'sum'),
                first_storage_m3=('stor', 'first'), last_storage_m3=('stor', 'last'),
                mean_W_Vc=('W_Vc', 'mean'), Vc_m3=('Vc_m3', 'first'), Pvol_m3=('Pvol_m3', 'first'),
                Evol_m3=('Evol_m3', 'first'))
    out = out.reset_index()
    # storage change across the year: last of this year minus last of previous year
    out = out.sort_values(['unit', 'yr'])
    prev = out.groupby('unit').last_storage_m3.shift(1)
    out['delta_storage_m3'] = out.last_storage_m3 - prev.fillna(out.first_storage_m3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('result_dir')
    ap.add_argument('scenario')
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--start-year', type=int, default=1985)
    ap.add_argument('--end-year', type=int, default=2023)
    ap.add_argument('--meta', help='transfer metadata csv (default: first *_transfer_metadata.csv in scenario_meta)')
    a = ap.parse_args()
    rd = Path(a.result_dir)
    txt = rd / 'native_runs' / a.scenario / 'TxtInOut'
    (rd / 'tables').mkdir(exist_ok=True)

    spec = importlib.util.spec_from_file_location('sf', PARSER)
    m = importlib.util.module_from_spec(spec)
    sys.argv = ['x']
    spec.loader.exec_module(m)
    m.ANALYSIS_START_YEAR = a.start_year
    m.ANALYSIS_END_YEAR = a.end_year
    meta = pd.read_csv(a.meta or glob.glob(str(rd / 'scenario_meta' / '*_transfer_metadata.csv'))[0])
    meta['scenario'] = a.scenario
    rows = m.parse_water_allocation(txt / 'water_allo_yr.txt', meta, a.scenario)
    res = m.summarize_water_allocation(rows, a.scenario)
    annual = None
    # summarize_water_allocation returns (summary, annual) in some versions; pick the one with 'yr'
    for obj in (res if isinstance(res, tuple) else (res,)):
        if isinstance(obj, pd.DataFrame) and 'yr' in obj.columns and 'transfer_role' in obj.columns:
            annual = obj
    if annual is None:
        df = rows.copy()
        raise SystemExit('annual table not produced by parser')
    annual.to_csv(rd / 'tables' / f'{a.scenario}_water_allocation_annual.csv', index=False, encoding='utf-8-sig')
    rows.to_csv(rd / 'tables' / f'{a.scenario}_water_allocation_raw.csv', index=False, encoding='utf-8-sig')

    if (txt / 'reservoir_day.txt').exists():       # A0 has no OFR objects
        rs = reservoir_summary(txt)
        rs.to_csv(rd / 'tables' / f'{a.scenario}_reservoir_year_summary.csv', index=False, encoding='utf-8-sig')
    else:
        rs = []
    print('tables written:', len(annual), 'annual rows;', len(rs), 'reservoir-years')

    if not a.keep:
        freed = 0
        for fn in BIG:
            p = txt / fn
            if p.exists():
                freed += p.stat().st_size
                p.unlink()
        print('pruned %.2f GB' % (freed / 1e9))


if __name__ == '__main__':
    main()
