# Scripts

Python 3 with `numpy`, `pandas` and, for spatial preprocessing, `geopandas`. The scripts are copied as used in the
study. They expect the original working layout: data folders such as
`swat_real_rerun_20260830/...` sit next to the scripts, and `apply_powerlaw.py` and
`build_scales.py` require user-supplied spatial inputs. Edit the path constants at the top of
each script before reuse.

| Script | Purpose |
|---|---|
| `apply_powerlaw.py` | Assigns pond capacities *V*<sub>j</sub> = *c* *A*<sub>j</sub><sup>*b*</sup> (*b* = 1.4367) and writes the aggregated OFR volumes into `hydrology.res` |
| `build_kappa.py` | Rewrites the hillslope-to-OFR routing fractions *f* = min(1, κ *A*<sub>OFR</sub>/*A*<sub>unit</sub>) in `rout_unit.con` |
| `build_scales.py` | Builds the S1–S3 configurations from the S4 baseline so that they differ only in OFR aggregation; `--canal` rescales the canal quotas (E2) |
| `preflight_check.py` | Checks inputs before a run (total OFR capacity, interception fraction, canal quotas, parameter files identical across scenarios) |
| `run_batch2.py` | Runs S0–S4 with one set of calibrated parameters |
| `run_matrix.py` | One-factor-at-a-time matrix (n, κ, PETCO) crossed with the aggregation scales |
| `dds_calibrate.py` | Two-layer multi-start DDS calibration (12 hydrology/soil, then 6 channel parameters) against log-transformed outlet flow |
| `eval_outlet.py` | Outlet performance metrics (logNSE, NSE, KGE, PBIAS) against Taoxi station |
| `summarize_run.py` | Builds water-allocation, paddy and reservoir summary tables, then prunes large outputs |
| `postrun_check.py` | Checks a finished run (canal cap respected, no direct canal supply to paddies in OFR scenarios, deficit thresholds) |

## Reuse boundary

These are archived method implementations, not a self-contained simulation workflow. The dated relative directories identify the original expected layout; those directories and all their data are excluded. Review study-specific constants, object naming, evaluation periods and file schemas before reuse.

- `apply_powerlaw.py`: provide pond geometry, LSU geometry, baseline inputs and aggregation membership. Set `SWAT_OFR_LSU` to the user's LSU shapefile.
- `build_scales.py`: provide complete baseline/scenario inputs and membership metadata. Set `SWAT_OFR_QSWAT_DB` to the user's QSWAT+ database.
- `build_kappa.py`: requires an external membership CSV with `LSUID` and `area_ha`.
- `dds_calibrate.py` and `eval_outlet.py`: require the user's observation CSV and model outputs; the code reads `date` and `obs_m3s`. No observation values are supplied.
- `summarize_run.py`: imports an external `run_supply_fix_a4_validation.py` parser absent from this package. Adapt or provide this dependency before use. It also deletes large output files unless `--keep` is supplied; use it only on a working copy.
- Batch and matrix runners depend on the preceding project layout, metadata and executable. Compilation of the modified SWAT+ source does not make these scripts independently runnable.

The retained names A0-A4 are legacy script identifiers. Map them explicitly to the scenarios in the manuscript version being used; do not infer irrigation-regime definitions from an old folder name or quota alone.
