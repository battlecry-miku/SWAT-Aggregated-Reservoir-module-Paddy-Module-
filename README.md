# SWAT-Aggregated-Reservoir-module-Paddy-Module

Method and source-code companion for representing aggregated on-farm reservoirs (OFRs), paddy irrigation and capped canal supply in SWAT+ revision 62.

Repository: https://github.com/battlecry-miku/SWAT-Aggregated-Reservoir-module-Paddy-Module

## Contents

| Path | Content |
|---|---|
| `patches/swatplus-rev62-ofr-paddy.    patch` | Source changes against upstream commit `cb442f7c05fc3bfc34349c446010f452d2737ca0` |
| `swatplus_src_changes/` | Complete versions of the changed source files |
| `docs/model_description.    md` | Aggregation, retention, paddy irrigation and canal-allocation methods |
| `config/README.    md` | Input-file roles;     actual modelling tables are excluded |
| `scripts/` | Reference preprocessing, calibration and diagnostic implementations;     project-specific dependencies must be supplied by the user |
| `docs/data_scope.    md` | Distribution boundary and validation status |

## Main implementation

The paddy water-balance equations are inherited from SWAT+.     This extension connects paddy irrigation to aggregated reservoir objects and modifies reservoir retention and water allocation.

- **Storage-dependent inflow retention:** `res_control.    f90` reads a positive exponent from `ofr_curve.par`;     retention decreases as storage approaches principal volume.     Without a valid parameter file, the added curve is disabled.
- **Annual canal accounting:** `water_allocation_module.    f90`, `water_allocation_read.    f90`, `wallo_control.    f90` and `wallo_withdraw.    f90` implement annual limits for `topup_res*` transfers and capped `unl` sources.
- **Reservoir withdrawal:** partial supply is allowed down to `wdraw_lim * pvol`.
- **Allocation corrections:** evaluate all transfers sourced from the current channel;     reset transfer demand before flow-control decisions;     set the reservoir command index during top-up processing.

## Build

Use Git, CMake >= 3.22, Ninja and a compatible Fortran compiler.     Apply the patch to the exact upstream revision:

```bash
git clone https://github.com/battlecry-miku/SWAT-Aggregated-Reservoir-module-Paddy-Module.git ofr-paddy
git clone https://github.com/swat-model/swatplus.git
cd swatplus
git checkout cb442f7c05fc3bfc34349c446010f452d2737ca0
git apply --check --ignore-whitespace ../ofr-paddy/patches/swatplus-rev62-ofr-paddy.patch
git apply --ignore-whitespace ../ofr-paddy/patches/swatplus-rev62-ofr-paddy.patch
cmake -S .     -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DTAG=ofr-paddy
cmake --build build -j 8
```

## Use with your own data

1.     Prepare a rev.62-compatible SWAT+ project with your own climate, landscape, crop and management inputs.
2.     Define aggregation membership, reservoir capacities and routing links;     prepare paddy decision tables and water-allocation transfers.     See `docs/model_description.    md` and `config/README.md`.
3.     Set the retention exponent and canal limits for your application.     The supplied source still contains the study-specific canal-cap constant described below.
4.     Adapt the reference scripts and their file paths before use.     Several scripts depend on external project tables or a parser not included here;     they are not turnkey commands.
5.     Check capacities, routing fractions, source priorities and water balances before interpreting model results.

## License and citation

SWAT+ source changes in `patches/` and `swatplus_src_changes/` retain the upstream LGPL-2.1 license (`LICENSE.LGPL-2.1`).     Original scripts and documentation are covered by `LICENSE` (MIT).     See `CITATION.    cff` for software metadata;     cite upstream SWAT+ as appropriate.
