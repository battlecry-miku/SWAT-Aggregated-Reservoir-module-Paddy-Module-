# Model description

Technical description of the paddy, on-farm reservoir (OFR) and canal-supply representation
implemented by this repository (SWAT+ rev.62 + `patches/swatplus-rev62-ofr-paddy.patch`) and
configured in `config/` (Taoxi S4/E1 baseline). Equation labels P1–P8 are local to this document.


## Representation of paddy fields, on-farm reservoirs and canal supply in SWAT+

### 1. Model framework and rationale

The watershed model was built with SWAT+ revision 62 (Bieger et al., 2017), whose paddy module
represents each rice field as a hydrological response unit (HRU) carrying a ponded-water storage
object with an adjustable outlet weir, and schedules ponding, irrigation and drainage through
decision tables (Arnold et al., 2018; Jeong et al., 2025). We used this module without changing
its paddy water-balance equations. We added two extensions to the source code: (i) a retention
curve that controls how much hillslope inflow an aggregated on-farm reservoir (OFR) unit can
capture as it fills, and (ii) annual caps on canal water within the SWAT+
water-allocation module. We also corrected three water-allocation routines
(see README). All simulations used a single executable built from the published patch.

### 2. Paddy water balance

Single-season middle rice (120-day cultivar, planted on 15 May and harvested on 30 September)
was grown on 182 paddy HRUs covering 53.7% of the catchment, followed by winter wheat
(planted 20 October, harvested 5 May). The daily ponded
depth *h* (mm) of a paddy HRU follows

  *h*<sub>t</sub> = *h*<sub>t−1</sub> + *P*<sub>t</sub> + *I*<sub>t</sub> − *E*<sub>w,t</sub> − *S*<sub>t</sub> − *D*<sub>t</sub>  (P1)

where *P* is precipitation, *I* is the irrigation water delivered to the field, *E*<sub>w</sub> is
evaporation from the ponded surface, *S* is seepage into the soil profile and *D* is weir
overflow. Evaporation from standing water decreases as the rice canopy closes
(Sakaguchi et al., 2014):

  *E*<sub>w,t</sub> = η<sub>p</sub> · max(0, 1 − LAI<sub>t</sub>/4) · PET<sub>t</sub>  (P2)

with η<sub>p</sub> = 0.75. PET is computed with Penman–Monteith and scaled by the calibrated
coefficient PETCO, which also sets rice transpiration and therefore the irrigation demand.
Seepage is

  *S*<sub>t</sub> = min(*h*<sub>t</sub>, 24 *K*<sub>p</sub>)  (P3)

with *K*<sub>p</sub> = 0.5 mm h⁻¹. *S* is further limited by the percolation capacity of the
underlying soil layers, so water that the soil cannot accept stays in the pond. Water above the
weir crest *H*<sub>w</sub> drains to the channel of the HRU's routing unit, computed at hourly
sub-steps with the SWAT+ weir equation

  *q* = 0.45 *A* *c*<sub>w</sub> *b* (*h* − *H*<sub>w</sub>)<sup>*k*<sub>w</sub></sup>  (P4)

where *A* is the HRU area (ha), *c*<sub>w</sub> = 1.83, *k*<sub>w</sub> = 1.5 and the weir width
*b* = 5 m. Hourly discharge cannot exceed the volume above the crest.

### 3. Paddy water management by decision tables

Three decision tables, applied to every paddy HRU, set field water management (table below):

1. **Weir operation.** *H*<sub>w</sub> = 60 mm from day of year 135 to 274 (15 May – 1 October)
   and 0 mm otherwise, so the field holds no water outside the rice season.
2. **Irrigation trigger.** While the weir is raised, irrigation is requested when
   *h* < 60 mm and more than 9 days have passed since the previous irrigation. The request
   refills the field to 60 mm:

     *I*\*<sub>t</sub> = max(0, 60 − *h*<sub>t</sub>) · *A* · 10  (m³)  (P5)

   With a field application efficiency of 0.9, a request from a dry field delivers at most
   54 mm. The rule produces rotational irrigation at intervals of about 10 days rather than
   daily top-up.
3. **Puddling.** A puddling action is scheduled at the start of the season (weir raised,
   *h* > 0, daily rainfall < 10 mm). No puddling parameter set (`puddle.ops`) was supplied, so
   this action does not change *K*<sub>p</sub> in the reported runs.

Irrigation demand is therefore not a prescribed quota. It follows the simulated ponded depth,
which itself depends on rainfall, PET, seepage and the water the sources can supply.

### 4. Irrigation sources and canal supply

The model reproduces the pond–canal ("melon-on-the-vine") supply chain of the Hangbu
irrigation district through the SWAT+ water-allocation module (table below):

- **Paddy withdrawals.** A paddy HRU first draws from the aggregated OFR of its own unit, down
  to a minimum storage of 0.05 *V*<sub>p</sub>, where *V*<sub>p</sub> is the principal
  (spillway-level) volume. Any shortfall is then taken from the local channel. Paddies in units
  without OFRs (15 of 182 HRUs) draw from the channel only. Demand still unmet after both
  sources is recorded as water deficit; no unlimited source backs up the paddies.
- **Canal top-up.** Canal water does not reach the paddies directly. It refills the OFRs:
  from April to October, an OFR whose storage falls below 0.85 *V*<sub>p</sub> requests canal
  water up to that level.
- **Canal caps.** Each OFR has an annual canal quota proportional to the paddy area it serves.
  The quotas sum to the 518 × 10⁶ m³ a⁻¹ head-works capacity in the demand-driven scenarios
  (E1), and were rescaled to sum to 350 × 10⁶ m³ a⁻¹ in the fixed-diversion scenarios (E2).
  We added annual accounting of these quotas, and of a basin-wide cap, to the water-allocation
  code.
- **No-OFR scenario (S0).** With no OFRs, paddies draw from the channel and then directly from
  the canal under the same caps.

### 5. Aggregated OFR storage and retention

OFRs inside each aggregation unit *i* are represented by one SWAT+ reservoir object. Its
principal volume *V*<sub>p,i</sub> is the sum of the capacities assigned to its member ponds,
*V*<sub>j</sub> = *c* *A*<sub>j</sub><sup>*b*</sup>, with *b* = 1.4367 and *c* chosen so that the
basin total is 56.50 × 10⁶ m³. The emergency volume is 1.3225 *V*<sub>p,i</sub> and the
corresponding surface area 1.15 *A*<sub>p,i</sub>, so surface area grows with the square root of
storage.

A fraction *f*<sub>i</sub> = min(1, κ *A*<sub>OFR,i</sub>/*A*<sub>u,i</sub>) of the unit's
hillslope runoff, with κ = 10, is routed towards the OFR; the remainder goes to the channel. Of
the day's inflow *R*<sub>i,t</sub>, the OFR retains a fraction that falls as storage approaches
*V*<sub>p</sub>:

  *K*<sub>i,t</sub> = [1 − min(1, *V*<sup>\*</sup><sub>i,t</sub> / *V*<sub>p,i</sub>)]<sup>*n*</sup>  (P6)

  Δ*V*<sub>i,t</sub> = *K*<sub>i,t</sub> *R*<sub>i,t</sub>,  bypass = (1 − *K*<sub>i,t</sub>) *R*<sub>i,t</sub>  (P7)

*V*\* is the storage when the inflow arrives, after any canal top-up and paddy withdrawal made
earlier on that day. *n* = 0.5 in the baseline. The bypassed water joins the reservoir outflow.

The OFR storage then gains direct precipitation and loses evaporation and seepage:

  *V*<sub>e</sub> = 10 η *E*<sub>p</sub> *A*,  *V*<sub>s</sub> = 240 *k*<sub>s</sub> *A*  (P8)

with η = 0.70, *k*<sub>s</sub> = 0.01 mm h⁻¹, and *A* (ha) updated daily from storage. Release
follows a decision table: no release below *V*<sub>p</sub>; storage between *V*<sub>p</sub> and
the emergency volume is drained back to *V*<sub>p</sub> over 7.39 days; any storage above the
emergency volume spills. Initial storage is 0.60 *V*<sub>p</sub>, and its effect is removed by
the 1981–1984 warm-up.


### 6. Process diagnostics

Outlet discharge cannot show whether paddy and pond water balances are plausible, so we report
three internal diagnostics:

1. A seasonal water-balance signature of a representative paddy HRU (ponded depth, rainfall,
   irrigation pulses, weir overflow and ET).
2. Simulated mean irrigation depth compared with the regional design quota for middle rice in a
   75% hydrological year (703 mm vs about 723 mm).
3. Simulated canal diversion compared with the 518 × 10⁶ m³ a⁻¹ head-works capacity.

Paddy deficit (unmet demand ÷ demand) and OFR storage ratio (*V*/*V*<sub>p</sub>) are reported
for each aggregation scale, because outlet-based metrics barely distinguish the scales
(Section 3.x).

---

### Settings (S4/E1 baseline)

| Component | Setting | Value | SWAT+ file / field |
|---|---|---|---|
| Rice crop | cultivar, planting–harvest | `rice120`; 15 May – 30 Sep | `plants.plt`, `management.sch` |
| Winter crop | winter wheat, planting–harvest | 20 Oct – 5 May | `management.sch` |
| Paddy HRUs | number; share of catchment | 182; 53.7% | `hru-data.hru` (surf_stor = `paddy0001`) |
| Weir height | rice season / off-season | 60 mm (DOY 135–274) / 0 mm | `lum.dtl` `pad_weir_single` |
| Weir equation | *c*<sub>w</sub>, *k*<sub>w</sub>, width | 1.83, 1.5, 5 m | `weir.res` `weir1` |
| Irrigation trigger | ponded depth; days since last irrigation | < 60 mm; > 9 d | `lum.dtl` `pad_irr_wallo` |
| Irrigation target | refill depth; application efficiency | 60 mm; 0.9 | `lum.dtl` (`irr_wallo` const), `irr.ops` `ponding90` |
| Paddy seepage | *K*<sub>p</sub> | 0.5 mm h⁻¹ | `hydrology.wet` `paddy` (k) |
| Ponded evaporation | η<sub>p</sub> | 0.75 | `hydrology.wet` `paddy` (evap) |
| Puddling | trigger; parameter set | weir up, *h* > 0, rain < 10 mm; **none supplied** | `lum.dtl` `puddle_single` |
| Paddy sources | order; OFR minimum storage | OFR → local channel; 0.05 *V*<sub>p</sub> | `water_allocation.wro` (`dtbl_lum`) |
| Canal top-up | season; target storage | Apr–Oct; 0.85 *V*<sub>p</sub> | `flo_con.dtl` `topup_res*` |
| Canal cap | annual, per OFR / basin | ∝ served paddy area; Σ = 518 (E1) or 350 (E2) × 10⁶ m³ | `water_allocation.wro` (amount); patch |
| OFR retention | exponent *n*; reference volume | 0.5; *V*<sub>p</sub> | `ofr_curve.par`; patch (`res_control.f90`) |
| OFR capacity | power-law exponent; basin total | *b* = 1.4367; 56.50 × 10⁶ m³ | `hydrology.res` |
| OFR losses | evaporation coefficient; bed seepage | 0.70; 0.01 mm h⁻¹ | `hydrology.res` (evap_co, k) |
| OFR release | below *V*<sub>p</sub> / *V*<sub>p</sub>–emergency / above emergency | hold / 7.39 d drawdown / spill | `res_rel.dtl` `S3_stage61_c_rel` |
| Initial OFR storage | fraction of *V*<sub>p</sub> | 0.60 | `om_water.ini` `ofr_init` |
