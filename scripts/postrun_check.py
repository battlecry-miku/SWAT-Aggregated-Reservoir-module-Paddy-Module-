# -*- coding: utf-8 -*-
"""Post-run check for the OFR aggregation study.

Reads the summary tables the run pipeline writes into <result_dir>/tables/
(`*reservoir_year_summary.csv` and `*water_allocation_annual.csv`), so it still
works after the large daily outputs have been pruned.  Run it after the first
few simulated years or after a full run:

    python postrun_check.py <result_dir> [--paddy-ha 84788] [--years 1985 2023]

Checks the irrigation ledger, the canal top-up cap, the closure of the pond
water budget, and whether canal water is retained by the ponds or merely passes
through them to the river.  Exit code 1 if any FAIL.
"""
import sys, io, os, glob, argparse
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CANAL_CAP = 518.0          # Mm3/a, basin canal head capacity stated in the paper
DEPTH_BAND = (300, 700)    # mm, common net irrigation quota of single mid-rice
UNMET_MAX_MEAN = 25.0      # %, reference acceptance: shortage should be episodic
PASS_THROUGH_MAX = 0.60    # flo_out / total pond inflow above this = ponds act as a funnel


def row(level, item, value, hint=''):
    print('  [%-4s] %-24s %s' % (level, item, value))
    if hint and level in ('FAIL', 'WARN'):
        print('         %-24s -> %s' % ('', hint))
    return level == 'FAIL'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('result_dir')
    ap.add_argument('--paddy-ha', type=float, default=84788.0)
    ap.add_argument('--years', type=int, nargs=2, default=(1985, 2023))
    ap.add_argument('--unmet-max', type=float, default=UNMET_MAX_MEAN,
                    help='acceptable mean unmet share (%%); the fixed-import control is water-limited '
                         'by construction and uses a documented, higher value')
    a = ap.parse_args()

    tdir = os.path.join(a.result_dir, 'tables')
    fr = glob.glob(os.path.join(tdir, '*reservoir_year_summary.csv'))
    fw = glob.glob(os.path.join(tdir, '*water_allocation_annual.csv'))
    if not fw:
        print('找不到汇总表：需要 tables/*water_allocation_annual.csv（含塘情景还需 *reservoir_year_summary.csv）')
        return 2
    w = pd.read_csv(fw[0], encoding='utf-8-sig')
    y0, y1 = a.years
    w = w[(w.yr >= y0) & (w.yr <= y1)]
    # A0 has no OFR objects -> no reservoir table; paddies may take canal water directly
    no_ofr = not fr
    r = pd.read_csv(fr[0], encoding='utf-8-sig') if fr else pd.DataFrame(columns=['yr'])
    r = r[(r.yr >= y0) & (r.yr <= y1)]
    ny = w.yr.nunique()
    print('=' * 78)
    print('%s   (%d–%d, %d 年)' % (a.result_dir, y0, y1, ny))
    print('=' * 78)
    fails = 0

    # ------------------------------------------------ irrigation ledger
    pad = w[w.transfer_role.str.startswith('paddy')].groupby('yr').sum(numeric_only=True) / 1e6
    top = w[w.transfer_role.eq('canal_topup_proxy_to_ofr')].groupby('yr')['withdraw_unl_m3'].sum() / 1e6
    D, Wr, Wc, Wu, U = (pad['demand_m3'], pad['withdraw_res_m3'], pad['withdraw_cha_m3'],
                        pad['withdraw_unl_m3'], pad['unmet_inferred_m3'])
    depth = D.mean() * 1e6 / (a.paddy_ha * 10)
    fails |= row('PASS' if DEPTH_BAND[0] <= depth <= DEPTH_BAND[1] else 'WARN', '稻田需水',
                 '%.1f Mm3/a，折合 %.0f mm（常见定额 %d–%d mm）' % (D.mean(), depth, *DEPTH_BAND),
                 '需水偏高：检查淹灌目标水深、晒田/落干、渗漏参数；目标须以灌区资料为据')
    if no_ofr:
        row('INFO', '稻田渠道直灌', 'A0：%.1f Mm3/a（最大 %.1f）' % (Wu.mean(), Wu.max()))
    else:
        # chosen design (user, 2026-09-11): in OFR scales all canal water enters the ponds first;
        # paddies draw pond -> channel only, never canal water directly
        fails |= row('PASS' if Wu.sum() == 0 else 'FAIL', '稻田无限源供水',
                     '%.2f Mm3/a' % Wu.mean(), '含塘各档稻田不得直接取渠道水（unl）：外调水须先入塘')
    share = 100 * U.mean() / D.mean()
    yrs_short = int((U > 0.01 * D).sum())
    # shortage should scale with drought: correlate annual shortage share with basin precipitation
    upct = 100 * U / D
    prec = {}
    for hw in glob.glob(os.path.join(a.result_dir, 'native_runs', '*', 'TxtInOut', 'hru_wb_yr.txt')):
        L = open(hw, errors='ignore').readlines()
        hdr = L[1].split()
        ip = hdr.index('precip')
        area = {}
        con = os.path.join(os.path.dirname(hw), 'hru.con')
        for l in open(con).readlines()[2:]:
            t = l.split()
            try:
                area[int(t[0])] = float(t[3])
            except (ValueError, IndexError):
                pass
        A = sum(area.values())
        for l in L[3:]:
            t = l.split()
            if len(t) > ip:
                y = int(t[3])
                prec[y] = prec.get(y, 0.0) + float(t[ip]) * area.get(int(t[4]), 0.0) / A
        break
    rp = upct.corr(pd.Series(prec)) if prec else float('nan')
    ok = share <= a.unmet_max and (rp <= -0.5 if prec else yrs_short < ny)
    fails |= row('PASS' if ok else 'FAIL', '未满足需水',
                 '均值 %.1f Mm3/a（%.1f%%），分位 10–90%% %.1f–%.1f%%；与年降水相关 r = %.2f'
                 % (U.mean(), share, upct.quantile(.1), upct.quantile(.9), rp),
                 '均值应 ≤ %.0f%%，且缺水随干旱加重（r ≤ −0.5）' % a.unmet_max)
    row('INFO', '稻田供水构成',
        '塘坝 %.1f  河道 %.1f  渠道直灌 %.1f  未满足 %.1f  (Mm3/a)' % (Wr.mean(), Wc.mean(), Wu.mean(), U.mean()))
    canal = top.add(Wu, fill_value=0.0)
    fails |= row('PASS' if canal.max() <= CANAL_CAP + 0.5 else 'FAIL', '外调水封顶',
                 '均值 %.1f，最大 %.1f Mm3/a（上限 %.0f）' % (canal.mean(), canal.max(), CANAL_CAP))
    if no_ofr:
        row('INFO', '塘坝水量', 'A0 无塘坝对象，跳过闭合与穿塘检查')
        print('\n' + ('全部通过。' if not fails else '存在 FAIL —— 修正后再铺开矩阵。'))
        return 1 if fails else 0

    # ------------------------------------------------ pond budget
    pb = r.groupby('yr')[['precip_m3', 'flo_in_m3', 'evap_m3', 'seep_m3', 'flo_out_m3',
                          'delta_storage_m3', 'Pvol_m3']].sum() / 1e6
    pb = pb.join(top.rename('topup')).join(Wr.rename('draw')).fillna(0.0)
    resid = pb.delta_storage_m3 - (pb.precip_m3 + pb.flo_in_m3 + pb.topup
                                   - pb.evap_m3 - pb.seep_m3 - pb.flo_out_m3 - pb.draw)
    thru = (pb.precip_m3 + pb.flo_in_m3 + pb.topup).mean()
    rel = abs(resid.mean()) / thru if thru else 0
    fails |= row('PASS' if rel <= 0.02 else 'FAIL', '塘坝水量闭合',
                 '残差 %.2f Mm3/a（通量的 %.1f%%）' % (resid.mean(), 100 * rel),
                 '闭合失败：取水或补水记账与塘坝蓄量不一致，结果不可用')
    ratio = pb.flo_out_m3.mean() / thru if thru else 0
    turnover = pb.flo_out_m3.mean() / pb.Pvol_m3.mean() if pb.Pvol_m3.mean() else 0
    fails |= row('PASS' if ratio <= PASS_THROUGH_MAX else 'FAIL', '外调水是否穿塘而过',
                 '出库 %.1f Mm3/a = 入塘总水量的 %.0f%%；年换水 %.1f 倍库容；给稻田仅 %.1f'
                 % (pb.flo_out_m3.mean(), 100 * ratio, turnover, pb.draw.mean()),
                 '塘坝在把外调水直接放回河道，而不是留给稻田：检查放水规则与补水触发')
    row('INFO', '塘坝年均蓄水率',
        '%.3f（多库多年平均）' % r['mean_W_Vc'].mean() if 'mean_W_Vc' in r else '—')

    print('\n' + ('全部通过。' if not fails else '存在 FAIL —— 修正后再铺开矩阵。'))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
