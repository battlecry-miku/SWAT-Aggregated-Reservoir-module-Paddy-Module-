# Input preparation guide

Actual case-study configuration tables have been removed from the current methods-only tree. Prepare these files within your own SWAT+ project; the names below identify input roles, not supplied datasets.

| Input | Role |
|---|---|
| `ofr_curve.par` | Positive retention exponent read by the modified reservoir routine |
| `reservoir.con`, `reservoir.res`, `hydrology.res` | Object links, principal/emergency storage and area, evaporation and seepage |
| `initial.res`, `om_water.ini`, `res_rel.dtl` | Initial conditions and reservoir-release rules |
| `rout_unit.con` | Runoff routing fractions and destination objects |
| `water_allocation.wro`, `flo_con.dtl` | Irrigation source priorities, canal transfers, decision rules and annual limits |
| `lum.dtl`, `management.sch`, `irr.ops` | Paddy irrigation triggers, crop operations and application efficiency |
| `hydrology.wet`, `wetland.wet`, `weir.res` | Paddy ponded-storage and drainage settings |
| `landuse.lum`, `plants.plt` | Land-use and crop definitions |

Retain consistent object identifiers across all files. Build complete rev.62-compatible inputs with the appropriate SWAT+ tooling; copying isolated rows is insufficient. Neither an aggregation membership table nor a calibrated parameter set is included.
