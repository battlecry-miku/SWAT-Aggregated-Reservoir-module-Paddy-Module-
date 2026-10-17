# -*- coding: utf-8 -*-
"""Compare simulated Taoxi outlet flow with observations.

    python eval_outlet.py <TxtInOut> [<TxtInOut> ...]

Reports NSE, logNSE, KGE, PBIAS and R2 for the calibration (1985-2016) and
validation (2017-2023) periods, mean annual runoff, and the FDC log-RMSE with
characteristic flows against the observed series.
"""
import sys, io, os, csv, datetime
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
OBS = os.path.join(HERE, 'swat_real_rerun_20260830', 'scale_conclusion_fdc_20260904',
                   'scale_conclusion_daily_flow_matrix_s0_s1_s2_s3cap500.csv')
P = np.arange(1, 100)


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


def read_sim(txt):
    s = {}
    with open(os.path.join(txt, 'taoxi_sim_daily.txt'), errors='ignore') as f:
        f.readline()
        for L in f:
            t = L.split()
            if len(t) > 6:
                try:
                    s[(int(t[3]), int(t[0]))] = float(t[6]) / 86400.0
                except ValueError:
                    pass
    return s


def stats(o, s):
    lo, ls = np.log(o), np.log(np.maximum(s, 1e-3))
    nse = 1 - np.sum((s - o) ** 2) / np.sum((o - o.mean()) ** 2)
    lnse = 1 - np.sum((ls - lo) ** 2) / np.sum((lo - lo.mean()) ** 2)
    r = np.corrcoef(o, s)[0, 1]
    kge = 1 - np.sqrt((r - 1) ** 2 + (s.std() / o.std() - 1) ** 2 + (s.mean() / o.mean() - 1) ** 2)
    # manuscript eq (10): logNSE on ln(1+Q) -- reported alongside the calibration objective ln(Q), floor 1e-3
    l1o, l1s = np.log1p(o), np.log1p(np.maximum(s, 0.0))
    lnse1p = 1 - np.sum((l1s - l1o) ** 2) / np.sum((l1o - l1o.mean()) ** 2)
    return nse, lnse, kge, 100 * np.sum(o - s) / np.sum(o), r * r, lnse1p


def fdc(q):
    q = np.sort(q)[::-1]
    p = (np.arange(1, len(q) + 1) - 0.44) / (len(q) + 0.12) * 100
    return np.interp(P, p, q)


def main(dirs):
    obs = read_obs()
    for txt in dirs:
        sim = read_sim(txt)
        print('=' * 78)
        print(txt)
        print('=' * 78)
        print('%-18s %6s %7s %7s %7s %8s %6s %9s' % ('时段', 'n', 'NSE', 'logNSE', 'KGE', 'PBIAS%', 'R2',
                                                   'lnNSE1+Q'))
        for lab, (y0, y1) in [('率定期 1985–2016', (1985, 2016)), ('验证期 2017–2023', (2017, 2023))]:
            k = [x for x in obs if y0 <= x[0] <= y1 and x in sim]
            if not k:
                print('%-18s  无重叠数据' % lab)
                continue
            o = np.array([obs[x] for x in k])
            s = np.array([sim[x] for x in k])
            print('%-18s %6d %7.3f %7.3f %7.3f %8.1f %6.3f %9.3f' % ((lab, len(k)) + stats(o, s)))
        k = [x for x in obs if 1985 <= x[0] <= 2023 and x in sim]
        if k:
            o = np.array([obs[x] for x in k])
            s = np.array([sim[x] for x in k])
            fo, fs = fdc(o), fdc(s)
            D = np.sqrt(np.mean((np.log10(np.maximum(fs, 1e-3)) - np.log10(fo)) ** 2))
            print('\n多年平均流量  实测 %.2f  模拟 %.2f m3/s  (年径流 %.0f / %.0f Mm3)'
                  % (o.mean(), s.mean(), o.mean() * 31.5576, s.mean() * 31.5576))
            print('FDC log-RMSE（相对实测）= %.4f' % D)
            print('特征流量  ' + '  '.join('Q%d %.2f/%.2f' % (p, np.interp(p, P, fo), np.interp(p, P, fs))
                                      for p in (5, 10, 50, 90)) + '   (实测/模拟)')


if __name__ == '__main__':
    main(sys.argv[1:])
