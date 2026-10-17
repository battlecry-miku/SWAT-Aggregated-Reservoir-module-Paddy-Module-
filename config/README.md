# Configuration tables (S4/E1 baseline)

Copied from the TxtInOut folder of the S4/E1 baseline: 165 Channel–LSU OFR units, demand-driven
canal supply capped at 518 × 10⁶ m³ a⁻¹, n = 0.5, κ = 10. Files marked *excerpt* contain only the
rows relevant to paddies or OFRs, with the original header lines.

| File | Content |
|---|---|
| `paddy/paddy_decision_tables.dtl` | *excerpt of `lum.dtl`*: `pad_weir_single` (weir 60 mm, DOY 135–274), `pad_irr_wallo` (irrigate when depth < 60 mm and > 9 days since the last irrigation), `puddle_single` |
| `paddy/management_rice2_rot.sch` | *excerpt of `management.sch`*: rice (`rice120`, 15 May – 30 Sep) followed by winter wheat (20 Oct – 5 May) |
| `paddy/hydrology_paddy.wet`, `paddy/wetland_paddy.wet` | Ponded-storage object of the paddy HRUs (seepage 0.5 mm h⁻¹, evaporation coefficient 0.75) |
| `paddy/weir.res` | Weir equation coefficients (`weir1`: c = 1.83, k = 1.5, width 5 m) |
| `paddy/irr.ops` | Irrigation operations; `ponding90` has application efficiency 0.9 |
| `paddy/landuse_paddy.lum`, `paddy/plants_rice120.plt` | *excerpts*: paddy land use and rice crop parameters |
| `ofr/ofr_curve.par` | Retention-curve exponent n read by the patched `res_control.f90` |
| `ofr/hydrology.res`, `ofr/reservoir.res` | Aggregated OFR objects: area and volume at principal and emergency level, evaporation coefficient 0.70, bed seepage 0.01 mm h⁻¹ |
| `ofr/res_rel_ofr.dtl` | *excerpt of `res_rel.dtl`*: release rule `S3_stage61_c_rel` (hold below *V*<sub>p</sub>, 7.39-day drawdown above it, spill above the emergency volume) |
| `ofr/initial.res`, `ofr/om_water_ofr_init.ini` | Initial storage: 0.60 of the principal volume |
| `allocation/water_allocation.wro` | 165 canal → OFR top-up transfers (`dtbl_con`) with annual quotas, and 182 paddy transfers (`dtbl_lum`: OFR → channel) |
| `allocation/flo_con.dtl` | Top-up decision tables: April–October, refill to 0.85 *V*<sub>p</sub> |
