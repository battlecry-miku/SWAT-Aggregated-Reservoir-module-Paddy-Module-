# -*- coding: utf-8 -*-
"""Build A1 / A2 / A3 configurations that differ from the fixed A4 only in OFR aggregation.

    python build_scales.py <out_root> [A1 A2 A3]

Base = fixed A4 (single rice, supply fix, top-up reset guard, ponding90 eff 0.9,
area-based caps).  Scale-specific objects (reservoir.con, reservoir.res,
hydrology.res, object.cnt, object.prt) come from the old result2_formal A1/A3
configurations; water allocation, top-up tables and routing-unit targets are
regenerated so that every rule matches A4.
"""
import sys, io, os, shutil, json, sqlite3
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply_powerlaw  # noqa: E402  (wraps stdout as UTF-8)

W = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'swat_real_rerun_20260830')
A4 = os.path.join(W, 'result2_areacap2_20260911', 'native_runs', 'A4_single_rice_areacap', 'TxtInOut')
OLD = os.path.join(W, 'result2_formal_20260910', 'native_runs')
MAP = os.path.join(W, 'result2_single_rice_20260911', 'scenario_meta',
                   'A4_single_rice_supplyfix_validation_paddy_hru_res_cha_map.csv')
QDB = ('C:/Users/Zhe Zhu/Documents/Codex/2026-07-06/new-chat/model/taoxi_qswat_official_ofr/'
       'taoxi_strict_station_upstream_v2/DatabaseBackups/Taoxi_Strict_Station_OFR_v2_bak_20260802-093059.sqlite')
SCALE_FILES = ['reservoir.con', 'reservoir.res', 'hydrology.res', 'object.cnt', 'object.prt']
REL = 'S3_stage61_c_rel'
CANAL = 518e6
# patched exe: canal cap also applies to direct canal irrigation (unl source on a non-topup transfer);
# pinned copy so rebuilds of the shared source tree cannot change it (see bin/README.txt)
EXE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin', 'swatplus_rev62_pvolVc_25a71e76.exe')
SKIP = lambda f: f.endswith(('_day.txt', '_mon.txt', '_yr.txt', '_aa.txt', '.log', '.out')) or f.startswith('fort.') \
    or f in ('taoxi_sim_daily.txt', 'success.fin')


# A2 = the 24 subbasin reservoirs of A3 merged into 7 zones on the SAME delineation (S7_merged24)
S7M = os.path.join(W, 's7_aggregation_20260909')
SCALE_DIR = {'A1': os.path.join(OLD, 'A1_BASE', 'TxtInOut'),
             'A2': os.path.join(S7M, 'native_runs', 'S7_merged24', 'TxtInOut'),
             'A3': os.path.join(OLD, 'A3_BASE', 'TxtInOut')}
A2_GROUPS = os.path.join(S7M, 'tables', 'S7_merged24_aggregated_reservoir_properties.csv')


def a3_to_a2():
    g = pd.read_csv(A2_GROUPS, encoding='utf-8-sig')
    return {int(o): int(r.res_id) for r in g.itertuples() for o in str(r.old_res_ids).split(';')}


def old_maps(scale):
    T = SCALE_DIR[scale]
    h2r, r2r = {}, {}
    for L in open(os.path.join(T, 'water_allocation.wro')).readlines()[4:]:
        t = L.split()
        if len(t) > 10 and t[1] == 'dtbl_lum' and 'res' in t:
            h2r[int(t[t.index('hru') + 1])] = int(t[t.index('res') + 1])
    for L in open(os.path.join(T, 'rout_unit.con')).readlines()[2:]:
        t = L.split()
        if 'res' in t:
            r2r[int(t[0])] = int(t[t.index('res') + 1])
    nres = sum(1 for l in open(os.path.join(T, 'hydrology.res')).readlines()[2:] if len(l.split()) >= 7)
    return T, h2r, r2r, nres


def hru_subbasin(D):
    """hru.con id -> QSWAT+ subbasin (hru.con gis_id = gis_hrus.id -> gis_lsus.subbasin)."""
    db = sqlite3.connect(QDB)
    lsu_sub = dict(db.execute('select id, subbasin from gis_lsus'))
    hru_lsu = dict(db.execute('select id, lsu from gis_hrus'))
    out = {}
    for l in open(os.path.join(D, 'hru.con')).readlines()[2:]:
        t = l.split()
        if len(t) > 3:
            out[int(t[0])] = lsu_sub[hru_lsu[int(t[2])]]
    return out


def subbasin_res(D):
    """subbasin -> reservoir.con id, from names res_sbNNN."""
    out = {}
    for l in open(os.path.join(D, 'reservoir.con')).readlines()[2:]:
        t = l.split()
        if len(t) > 2 and t[1].startswith('res_sb'):
            out[int(t[1][6:])] = int(t[0])
    return out


def write_meta(out_root, scale, caps, pad, channel_only=False, canal_cap=None):
    """Transfer metadata in the same layout as the A4 scenario_meta file (read by summarize_run)."""
    rtu = {int(r.hru_id): r.rtu_id for r in pd.read_csv(MAP).itertuples()}
    rows, k = [], 0
    for j, c in caps.items():
        k += 1
        rows.append(dict(transfer_id=k, transfer_role='canal_topup_proxy_to_ofr', source_count=1,
                         receiver_type='res', receiver_id=j, local_res_id=j, src1_typ='unl', src1_frac=1.0,
                         src1_wdraw_lim=0.0, capacity_share=c / CANAL, topup_annual_cap_m3=c,
                         topup_annual_cap_Mm3=c / 1e6, topup_daily_cap_m3=c / 214.0))
    for h, res, cha in pad:
        k += 1
        r = dict(transfer_id=k, receiver_type='hru', receiver_id=h, local_cha_id=cha, hru_id=h, rtu_id=rtu[h])
        if canal_cap:
            c = canal_cap[h]
            r.update(transfer_role='paddy_channel_then_direct_canal', source_count=2,
                     src1_typ='cha', src1_frac=1.0, src1_wdraw_lim=0.0,
                     src2_typ='unl', src2_frac=0.0, src2_wdraw_lim=0.0, capacity_share=c / CANAL,
                     topup_annual_cap_m3=c, topup_annual_cap_Mm3=c / 1e6)
        elif channel_only:
            r.update(transfer_role='paddy_channel_only_no_local_res', source_count=1,
                     src1_typ='cha', src1_frac=1.0, src1_wdraw_lim=0.0)
        else:
            r.update(transfer_role='paddy_priority_res_then_channel', source_count=2, local_res_id=res,
                     src1_typ='res', src1_frac=1.0, src1_wdraw_lim=0.05,
                     src2_typ='cha', src2_frac=0.0, src2_wdraw_lim=0.0)
        rows.append(r)
    cols = ['scenario', 'transfer_id', 'transfer_role', 'source_count', 'receiver_type', 'receiver_id',
            'local_res_id', 'local_cha_id', 'hru_id', 'rtu_id', 'src1_typ', 'src1_frac', 'src1_wdraw_lim',
            'capacity_share', 'topup_annual_cap_m3', 'topup_annual_cap_Mm3', 'topup_daily_cap_m3',
            'src2_typ', 'src2_frac', 'src2_wdraw_lim']
    d = pd.DataFrame(rows).assign(scenario='%s_base' % scale).reindex(columns=cols)
    os.makedirs(os.path.join(out_root, 'scenario_meta'), exist_ok=True)
    d.to_csv(os.path.join(out_root, 'scenario_meta', '%s_base_transfer_metadata.csv' % scale), index=False)


def build(scale, out_root):
    T, h2r, r2r, nres = old_maps(scale)
    D = os.path.join(out_root, '%s_base' % scale, 'TxtInOut')
    if os.path.exists(D):
        shutil.rmtree(D)
    os.makedirs(D)
    for f in os.listdir(A4):
        if not SKIP(f) and os.path.isfile(os.path.join(A4, f)):
            shutil.copy2(os.path.join(A4, f), os.path.join(D, f))
    for f in SCALE_FILES:
        shutil.copy2(os.path.join(T, f), os.path.join(D, f))
    shutil.copy2(EXE, os.path.join(D, 'swatplus.exe'))    # same binary for every scale (A4 output verified identical)

    # one release rule for every scale
    L = open(os.path.join(D, 'reservoir.res')).read().splitlines()
    for i in range(2, len(L)):
        t = L[i].split()
        if len(t) >= 5:
            t[4] = REL
            L[i] = ' '.join(t)
    open(os.path.join(D, 'reservoir.res'), 'w').write('\n'.join(L) + '\n')

    # paddy HRUs (same 182 as A4) -> scale reservoir; channel ids from A4 map
    m = pd.read_csv(MAP)
    area = {}
    for l in open(os.path.join(D, 'hru.con')).readlines()[2:]:
        t = l.split()
        try:
            area[int(t[0])] = float(t[3])
        except (ValueError, IndexError):
            pass
    # paddy -> reservoir of its own subbasin (QSWAT+ database); A2 then merges subbasins into zones
    grp = a3_to_a2() if scale == 'A2' else None
    if scale in ('A2', 'A3'):
        sub_res, h_sub = subbasin_res(SCALE_DIR['A3']), hru_subbasin(D)
    pad = []
    for r in m.itertuples():
        h = int(r.hru_id)
        if scale == 'A1':
            res = 1
        else:
            res = sub_res[h_sub[h]]
            if grp:
                res = grp[res]
            elif h in h2r and h2r[h] != res:
                raise SystemExit('A3 映射与旧配置不一致: hru %d' % h)
        pad.append((h, res, int(r.local_cha_id)))
    served = {}
    for h, res, _ in pad:
        served[res] = served.get(res, 0.0) + area[h]
    tot = sum(served.values())
    caps = {j: (served[j] / tot * CANAL if j in served else 1.0) for j in range(1, nres + 1)}

    # water allocation
    hdr = open(os.path.join(A4, 'water_allocation.wro')).read().splitlines()[:5]
    hdr[0] = 'water_allocation.wro: %s aggregation, reservoir priority then local channel, area-based canal caps' % scale
    hdr[3] = '%-25s %-17s %d' % ('supplyfix_ofr_paddy', 'demand', nres + len(pad))
    rows, k = [], 0
    for j in range(1, nres + 1):
        k += 1
        rows.append('%d dtbl_con topup_res%03d %.3f sr 1 null unl 0 none 0 null 0.000 1.000 n res %d 0'
                    % (k, j, caps[j], j))
    for h, res, cha in pad:
        k += 1
        rows.append('%d dtbl_lum pad_irr_wallo 0.000000 sr 2 null res %d none 0 null 0.050 1.000 n '
                    'cha %d none 0 null 0.000 0.000 y hru %d 0' % (k, res, cha, h))
    open(os.path.join(D, 'water_allocation.wro'), 'w').write('\n'.join(hdr + rows) + '\n')

    # top-up decision tables with the reset guard
    # layout: title / count / [blank, "name conds alts acts", table]...  -- keep each table's header
    F = open(os.path.join(A4, 'flo_con.dtl')).read().splitlines()
    s = next(i for i, l in enumerate(F) if l.split()[:1] == ['topup_res001'])
    e = next(i for i in range(s + 1, len(F)) if F[i].split()[:1] and F[i].split()[0].startswith('topup_res'))
    e2 = e
    while e2 > s and (not F[e2 - 1].strip() or F[e2 - 1].split()[0] == 'name'):
        e2 -= 1
    tmpl, sep = F[s:e2], F[e2:e]
    out = [F[0].rstrip(), str(nres)] + F[2:s]
    for j in range(1, nres + 1):
        if j > 1:
            out += sep
        for l in tmpl:
            t = l.split()
            if t and t[0] == 'topup_res001':
                l = l.replace('topup_res001', 'topup_res%03d' % j, 1)
            elif len(t) > 2 and t[1] == 'res' and t[2] == '1':
                l = l.replace(' res         1 ', ' res %9d ' % j, 1) if ' res         1 ' in l else \
                    ' '.join(t[:2] + [str(j)] + t[3:])
            out.append(l)
    open(os.path.join(D, 'flo_con.dtl'), 'w').write('\n'.join(out) + '\n')

    # routing units: keep A4 fractions, retarget to the scale reservoir
    r2r_a3 = old_maps('A3')[2] if scale == 'A2' else r2r
    L = open(os.path.join(D, 'rout_unit.con')).read().splitlines()
    for i in range(2, len(L)):
        t = L[i].split()
        if 'res' in t:
            p, u = t.index('res'), int(t[0])
            new = 1 if scale == 'A1' else (grp[r2r_a3[u]] if grp else r2r[u])
            if grp and u in r2r and r2r[u] != new:
                raise SystemExit('A2 汇流单元映射与 S7_merged24 不一致: rtu %d' % u)
            t[p + 1] = str(new)
            L[i] = ' '.join(t)
    open(os.path.join(D, 'rout_unit.con'), 'w').write('\n'.join(L) + '\n')

    # capacity prior: area-volume power law (methods eqs 15-17), same basin total in every scale
    apply_powerlaw.write(D, scale, apply_powerlaw.B_DEFAULT)

    meta = {'scale': scale, 'n_res': nres, 'n_paddy_hru': len(pad), 'release_rule': REL,
            'capacity_prior': 'power law b=%.4f' % apply_powerlaw.B_DEFAULT,
            'n_res_serving_paddy': len(served), 'cap_total_Mm3': sum(caps.values()) / 1e6,
            'caps_Mm3': {j: round(c / 1e6, 4) for j, c in caps.items()}}
    json.dump(meta, open(os.path.join(out_root, '%s_base_meta.json' % scale), 'w', encoding='utf-8'), indent=1)
    write_meta(out_root, scale, caps, pad)
    print('%s: %d 个塘坝对象（%d 个供稻田），%d 片稻田，额度合计 %.1f Mm3 → %s'
          % (scale, nres, len(served), len(pad), meta['cap_total_Mm3'], D))


def build_a0(out_root, canal=True):
    """A0: no OFR objects.  Paddies draw from their local channel first; with canal=True the
    shortfall is irrigated directly with canal water, each paddy capped at its area share of the
    518 Mm3/a (transfer `amount`, enforced by the unl-cap patch in wallo_control/wallo_withdraw).
    canal=False ('A0ch') is the channel-only reference.
    Routing = A4 with the reservoir branch folded back into the channel (identical to the
    official no-OFR scenario S0_stage61_no_ofr_stage59best, checked 187/187 rows)."""
    tag = 'A0' if canal else 'A0ch'
    D = os.path.join(out_root, '%s_base' % tag, 'TxtInOut')
    if os.path.exists(D):
        shutil.rmtree(D)
    os.makedirs(D)
    for f in os.listdir(A4):
        if not SKIP(f) and os.path.isfile(os.path.join(A4, f)):
            shutil.copy2(os.path.join(A4, f), os.path.join(D, f))

    L = open(os.path.join(D, 'rout_unit.con')).read().splitlines()
    for i in range(2, len(L)):
        t = L[i].split()
        if 'res' in t:
            p = t.index('res')
            fr = float(t[p + 3])
            del t[p:p + 4]
            q = t.index('sdc')
            t[q + 3] = '%.5f' % (float(t[q + 3]) + fr)
            t[12] = str(int(t[12]) - 1)
            L[i] = ' '.join(t)
    open(os.path.join(D, 'rout_unit.con'), 'w').write('\n'.join(L) + '\n')

    L = open(os.path.join(D, 'object.cnt')).read().splitlines()
    t = L[2].split()
    nres = int(t[10])
    t[3], t[10] = str(int(t[3]) - nres), '0'
    L[2] = ' '.join(t)
    open(os.path.join(D, 'object.cnt'), 'w').write('\n'.join(L) + '\n')

    # reservoir.con and flo_con.dtl off; weir/wetland files stay (paddy bunds)
    L = open(os.path.join(D, 'file.cio')).read().splitlines()
    for i, l in enumerate(L):
        t = l.split()
        if t[:1] == ['connect']:
            L[i] = l.replace('reservoir.con', 'null         ', 1)
        elif t[:1] == ['decision_table']:
            L[i] = l.replace('flo_con.dtl', 'null       ', 1)
    open(os.path.join(D, 'file.cio'), 'w').write('\n'.join(L) + '\n')

    m = pd.read_csv(MAP)
    area = {int(l.split()[0]): float(l.split()[3]) for l in open(os.path.join(D, 'hru.con')).readlines()[2:]
            if len(l.split()) > 3 and l.split()[0].isdigit()}
    tot = sum(area[int(r.hru_id)] for r in m.itertuples())
    hdr = open(os.path.join(A4, 'water_allocation.wro')).read().splitlines()[:5]
    hdr[3] = '%-25s %-17s %d' % ('supplyfix_ofr_paddy', 'demand', len(m))
    if canal:
        hdr[0] = 'water_allocation.wro: A0 no OFR, local channel first then direct canal irrigation, area-based caps'
        rows = ['%d dtbl_lum pad_irr_wallo %.3f sr 2 null cha %d none 0 null 0.000 1.000 n '
                'unl 0 none 0 null 0.000 0.000 y hru %d 0'
                % (k, area[int(r.hru_id)] / tot * CANAL, int(r.local_cha_id), int(r.hru_id))
                for k, r in enumerate(m.itertuples(), 1)]
    else:
        hdr[0] = 'water_allocation.wro: A0ch no OFR, paddies draw from local channel only, no canal water'
        rows = ['%d dtbl_lum pad_irr_wallo 0.000000 sr 1 null cha %d none 0 null 0.000 1.000 n hru %d 0'
                % (k, int(r.local_cha_id), int(r.hru_id)) for k, r in enumerate(m.itertuples(), 1)]
    open(os.path.join(D, 'water_allocation.wro'), 'w').write('\n'.join(hdr + rows) + '\n')
    shutil.copy2(EXE, os.path.join(D, 'swatplus.exe'))    # unl cap lives only in the patched exe

    meta = {'scale': tag, 'n_res': 0, 'n_paddy_hru': len(m), 'removed_res_objects': nres,
            'water_source': 'local channel, then direct canal' if canal else 'local channel only',
            'canal_cap_total_Mm3': CANAL / 1e6 if canal else 0.0}
    json.dump(meta, open(os.path.join(out_root, '%s_base_meta.json' % tag), 'w', encoding='utf-8'), indent=1)
    write_meta(out_root, tag, {}, [(int(r.hru_id), None, int(r.local_cha_id)) for r in m.itertuples()],
               channel_only=True,
               canal_cap={int(r.hru_id): area[int(r.hru_id)] / tot * CANAL for r in m.itertuples()} if canal else None)
    print('%s: 去掉 %d 个塘坝对象，%d 片稻田%s → %s'
          % (tag, nres, len(m), '先河道后渠道直灌（按面积分 518 额度）' if canal else '仅从河道取水', D))


if __name__ == '__main__':
    argv = sys.argv[1:]
    if '--canal' in argv:                      # common annual canal quota (Mm3/a), e.g. fixed-import control
        i = argv.index('--canal')
        CANAL = float(argv[i + 1]) * 1e6
        del argv[i:i + 2]
        print('外调水年额度设为 %.1f Mm3/a' % (CANAL / 1e6))
    out_root = argv[0]
    for sc in (argv[1:] or ['A1', 'A2', 'A3']):
        if sc in ('A0', 'A0ch'):
            build_a0(out_root, canal=(sc == 'A0'))
        else:
            build(sc, out_root)
