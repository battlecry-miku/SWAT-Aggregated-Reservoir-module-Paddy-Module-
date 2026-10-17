# swatplus-ofr-paddy

SWAT+ revision 62 extended for **aggregated on-farm reservoirs (OFRs) coupled with paddy
irrigation and capped canal supply**, as used in:

> Zhu, Z., Li, Y., Pei, S., Zhang, C., Zhou, Y. Aggregation scale of on-farm reservoir
> representation and its cumulative effect on simulated surface hydrology and irrigation supply
> in a paddy irrigation district. *In preparation.*

Case study: the Taoxi catchment (1,577.85 km², 4,298 OFRs) in the Hangbu irrigation district,
China. The paddy water balance is the stock SWAT+ paddy module (Jeong et al., 2025). This
repository adds an OFR retention curve, annual canal caps, and fixes to the water-allocation
routines, plus the input tables and scripts behind the paper.

## Contents

| Path | What it is |
|---|---|
| `patches/swatplus-rev62-ofr-paddy.patch` | All source changes against upstream SWAT+ commit [`cb442f7`](https://github.com/swat-model/swatplus/commit/cb442f7c05fc3bfc34349c446010f452d2737ca0) (rev.62) |
| `swatplus_src_changes/` | The same changed files in full, for reading without applying the patch |
| `config/paddy/` | Paddy decision tables, management schedule, ponded-storage and weir parameters, irrigation operation, rice parameters |
| `config/ofr/` | OFR retention exponent, reservoir objects and hydrology (165 aggregated units), release rule, initial storage |
| `config/allocation/` | Water-allocation transfers (OFR → channel for paddies; canal → OFR top-up) and the canal top-up decision tables |
| `scripts/` | Pre-processing (scale construction, power-law capacity, κ routing fractions), checks, calibration and post-processing (see `scripts/README.md`) |
| `docs/model_description.md` | Equations and decision rules of the paddy, OFR and canal-supply representation, with a settings table that maps every value to its file |

All configuration files come from the S4/E1 baseline (165 Channel–LSU OFR units, demand-driven
canal supply). The coarser scales S1–S3 and the fixed-diversion runs E2 are generated from it
with `scripts/build_scales.py`.

## Changes relative to SWAT+ rev.62

| File(s) | Change | Used in the paper's runs |
|---|---|---|
| `res_control.f90` | OFR retention curve: each day the reservoir keeps a fraction K = (1 − V/V<sub>p</sub>)<sup>n</sup> of its inflow and the rest bypasses to its outflow. n is read from `ofr_curve.par`; the curve is off if that file is absent. | yes |
| `water_allocation_module.f90`, `water_allocation_read.f90`, `wallo_control.f90`, `wallo_withdraw.f90` | Annual canal caps: a basin-wide cap (518 × 10⁶ m³, hard-coded) and per-transfer annual `amount`. They apply to `topup_res*` transfers and to any other transfer drawing from an `unl` source. | yes |
| `wallo_withdraw.f90` | Reservoir source: partial withdrawal down to `wdraw_lim × pvol`. Stock code rejected the whole demand whenever full withdrawal would breach the minimum. | yes |
| `sd_channel_control3.f90` | Channel-sourced transfers: every transfer that uses the current channel as source is evaluated. Stock code only checked the current transfer pointer. | yes |
| `sd_channel_control3.f90` | Stream temperature (`ch_temp`) call disabled, so the build is valid for water quantity only. | yes |
| `wallo_demand.f90` | `trn_m3` is reset before flow-control decision tables are evaluated. | yes |
| `wallo_control.f90` | The active command index is set to the reservoir object when `res_control` is called after a top-up. | yes |
| `ch_temp.f90`, `hyd_connect.f90` | Array-bound guards and comment edits. | guards only |
| `basin_module.f90`, `cal_parm_select.f90`, `sq_volq.f90`, `sq_surfst.f90`, `ero_ovrsed.f90`, `sq_satexcess.f90` (new) | Optional saturation-excess runoff (`gampt = 2`). | **no**: all runs use `gampt = 0` (curve number) |
| `CMakeLists.txt` | GNU release flags: `-fcheck`/`-ffpe-trap` moved to debug builds; `-O2`. | build only |

## Build

Requires CMake ≥ 3.22, Ninja and gfortran. The paper used GNU Fortran 15.2.0 (conda-forge),
CMake 4.3.4 and Ninja on Windows x64.

```bash
git clone https://github.com/swat-model/swatplus.git && cd swatplus
git checkout cb442f7c05fc3bfc34349c446010f452d2737ca0
git apply --ignore-whitespace ../swatplus-ofr-paddy/patches/swatplus-rev62-ofr-paddy.patch
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DTAG=ofr-paddy
cmake --build build -j 8
```

### Reproducibility check

The executable used for all simulations in the paper has SHA-256

```
25a71e767f972df5b693991f2ff08b9cd08d8d9d4702816738962c51825de84a
```

It is attached to the GitHub release rather than committed to the repository. Building the patch
again with the toolchain above gave an executable whose bytes differ (SHA-256 `4fd7878b…`).
Running both on the S4/E1 baseline for 1981–1982 gave 24 output files in which all 1,184,510
numeric values were identical; only the run-time stamps in the title lines differed.

## Running a scenario

1. Build a SWAT+ project with QSWAT+ / SWAT+ Editor (rev.62 inputs).
2. Replace the paddy, reservoir and water-allocation tables with those in `config/` (or generate
   them with `scripts/`), and put `ofr_curve.par` in the TxtInOut folder.
3. Run `scripts/preflight_check.py <TxtInOut>` before each long run. It checks the total OFR
   capacity, interception fraction, canal quotas and parameter-file consistency across scenarios.
4. Run the executable in the TxtInOut folder.

## Data not included

Daily discharge at Taoxi station, station meteorology, the DEM, the soil and land-use rasters,
and the OFR polygon inventory are not redistributed here. The paper's data availability
statement says how to obtain them.

## Known limitations

- Water quantity only: stream temperature is switched off, and water-quality routines were not
  tested with the patched topology.
- The basin-wide canal cap (518 × 10⁶ m³) is hard-coded in `water_allocation_module.f90`.
  Lower caps are imposed through the per-transfer `amount` column.
- The puddling decision table (`puddle_single`) is scheduled, but no `puddle.ops` is supplied.
  Puddling therefore has no effect on paddy seepage in these runs.
- The retention exponent n is a single basin-wide value.

## License

The SWAT+ source code and the modified files are distributed under the GNU Lesser General
Public License v2.1, the license of upstream SWAT+ (see `LICENSE`). Configuration tables,
scripts and documentation are released under the same license unless stated otherwise.

## Citation

Please cite the paper above and SWAT+ itself (see upstream `CITATION.cff`). Machine-readable
metadata for this repository are in `CITATION.cff`.
