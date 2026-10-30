# Methods

This document describes the algorithms represented by the supplied source patch and reference scripts. It does not distribute the study catchment, parameter tables or simulation results. Numerical settings embedded in the reference code are application-specific and must be reviewed before reuse.

## 1. Aggregate reservoir representation

Assign each pond to an aggregation unit using an explicit spatial membership rule. A pond must be assigned once, and its membership must be checked before summing area and storage.

The reference capacity method uses `V_j = c A_j^b`, where `c = V_total / sum(A_j^b)`. Unit capacity is the sum of member-pond capacities. Holding the same inventory and total capacity across scales separates the effect of aggregation from changes in total storage. See `scripts/apply_powerlaw.py`.

Route a fraction `f_i = min(1, kappa * A_OFR,i / A_unit,i)` of unit hillslope runoff towards the aggregated reservoir, and the remainder towards the channel. Areas must use consistent units. The geometric routing fraction and the storage-dependent retention fraction below are separate operations. See `scripts/build_kappa.py`.

## 2. Storage-dependent inflow retention

At the point when inflow is processed, let `V` be reservoir storage and `Vp` principal volume:

```text
s = min(1, max(0, V / Vp))
K = min(1, max(0, (1 - s)^n))
retained inflow = K * inflow
bypass flow = (1 - K) * inflow
```

`res_control.f90` adds bypass flow to reservoir outflow and passes retained inflow into the reservoir balance. Other reservoir processes, including precipitation, evaporation, seepage and release, remain in the SWAT+ calculation sequence. The storage used here reflects operations already executed that day.

The exponent is read once from `ofr_curve.par` in the run directory, as either a key followed by a value or a value alone. A missing, unreadable or non-positive value leaves this added curve disabled. The curve requires positive inflow and non-negligible principal volume. It is not restricted by an OFR-specific object flag.

## 3. Paddy water management

Paddy ponded storage and its water-balance equations come from the upstream SWAT+ module. Decision tables control weir elevation, irrigation triggers and crop-management timing. Irrigation requests depend on simulated ponded depth and management rules; source withdrawals are constrained by available water and allocation priorities.

For reuse, define the target ponding depth, minimum irrigation interval, field application efficiency, crop calendar, seepage and evaporation parameters in the user's project. A scheduled puddling action requires a valid puddling operation and parameter set to affect the calculation; do not infer a seepage change from the schedule alone.

## 4. Water sources and annual canal limits

The study's conceptual supply sequence is aggregated OFR followed by the local channel for paddy demand, with canal water used to top up OFRs. Units without OFRs and a no-OFR counterfactual require explicit alternative transfer definitions. The actual source order and object links are input configuration, not reconstructed automatically from this methods package.

`wallo_withdraw.f90` permits partial reservoir withdrawal above the minimum storage `wdraw_lim * pvol`. Remaining demand can then be handled by the configured source sequence.

`wallo_control.f90` recognizes transfer names beginning with `topup_res` and separately handles other transfers drawing from an `unl` source. It resets annual counters when the simulation year changes, restricts withdrawals to remaining limits and updates usage from withdrawals. A positive transfer `amount` supplies a transfer-level annual ceiling.

The shared ceiling is the `wallo_topup_cap_m3` source constant. Its counters are indexed by allocation object, so the intended basin-wide interpretation relies on the configuration using one such object. The retained code value is 518,000,000 m3; it is a model assumption, not a supplied observation. An annual cap must not be described as a fixed daily diversion regime without a separate scheduling rule.

## 5. Comparisons and diagnostics

For aggregation experiments, hold climate forcing, crop management, total reservoir capacity and applicable supply constraints consistent. Change membership and corresponding routing/allocation links deliberately. Document exceptions rather than treating all scenarios as automatically equivalent.

Check both outlet flow and internal allocation: delivered irrigation, withdrawals by source, unmet demand, reservoir storage and canal use. Verify time steps, units, initial storage and storage changes before interpreting a water balance. Outlet agreement alone does not validate internal transfers or demonstrate scale convergence.

Calibration, batch execution and post-processing scripts are supplied as reference implementations. Their original project dependencies are listed in `scripts/README.md`; no catchment data or completed model runs accompany them.
