      subroutine sq_satexcess

!!    ~ ~ ~ PURPOSE ~ ~ ~
!!    Predicts daily surface runoff using a saturation-excess (Xinanjiang
!!    "蓄满产流") tension-water-capacity curve, replacing the SCS curve number
!!    for upland HRUs. Selected by bsn_cc%gampt == 2. Runoff begins once the
!!    soil column approaches field capacity and grows nonlinearly with the
!!    saturated area fraction, reproducing the sharp daily flood peaks that the
!!    curve number smooths out in humid, saturation-excess catchments.
!!
!!    The scheme reuses SWAT+'s own soil-water state, so no new state is added
!!    and mass balance closes downstream via inflpcp = precip_eff - surfq.
!!    Paddy / wetland HRUs (ires > 0) never call this routine; their ponded
!!    water balance in wetland_control is untouched.

!!    ~ ~ ~ INCOMING VARIABLES ~ ~ ~
!!    name              |units    |definition
!!    soil(j)%sw        |mm H2O   |current water stored in the soil profile
!!    soil(j)%sumfc     |mm H2O   |water held in the profile at field capacity
!!    bsn_prm%satx_b    |none     |tension-water-capacity curve exponent
!!    bsn_prm%satx_wmfac|none     |WM as a fraction of field-capacity storage
!!    precip_eff        |mm H2O   |effective precipitation reaching the surface

!!    ~ ~ ~ OUTGOING VARIABLES ~ ~ ~
!!    surfq(:)          |mm H2O   |surface runoff generated for the day

!!    ~ ~ ~ ~ ~ ~ END SPECIFICATIONS ~ ~ ~ ~ ~ ~

      use basin_module, only : bsn_prm
      use hru_module, only : surfq, ihru, precip_eff
      use soil_module

      implicit none

      integer :: j = 0     !none    |HRU number
      real :: wm = 0.      !mm H2O  |areal-mean tension water capacity
      real :: wmm = 0.     !mm H2O  |maximum point tension water capacity
      real :: w = 0.       !mm H2O  |current tension water storage (capped at wm)
      real :: a = 0.       !mm H2O  |ordinate of current storage on the curve
      real :: pe = 0.      !mm H2O  |effective precipitation
      real :: r = 0.       !mm H2O  |generated runoff
      real :: bexp = 0.    !none    |curve exponent

      j = ihru
      bexp = bsn_prm%satx_b
      wm = bsn_prm%satx_wmfac * soil(j)%sumfc
      if (wm < 1.) wm = 1.
      w = soil(j)%sw
      if (w > wm) w = wm
      if (w < 0.) w = 0.

      pe = precip_eff
      surfq(j) = 0.
      if (pe > 0.) then
        wmm = wm * (1. + bexp)
        if (w >= wm) then
          a = wmm
        else
          a = wmm * (1. - (1. - w / wm) ** (1. / (1. + bexp)))
        end if
        if (pe + a < wmm) then
          r = pe - (wm - w) + wm * (1. - (pe + a) / wmm) ** (1. + bexp)
        else
          r = pe - (wm - w)
        end if
        if (r < 0.) r = 0.
        if (r > pe) r = pe
        surfq(j) = r
      end if

      return
      end subroutine sq_satexcess
