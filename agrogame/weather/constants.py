"""
Named constants used in weather/ET calculations.

Primary sources:
- FAO Irrigation and Drainage Paper 56 (FAO-56):
  Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998).
  Crop evapotranspiration – Guidelines for computing crop water requirements.
  Rome: FAO. Printable PDF: https://www.fao.org/3/x0490e/x0490e00.htm
- NASA POWER Daily API: https://power.larc.nasa.gov/docs/services/api/temporal/daily/

Notes:
- Constants are defined once to avoid "magic numbers" and to make the
  origin of values explicit.
- Where the literature offers slightly different coefficients, we use the
  FAO-56 recommended values.
"""

# Shortwave albedo for reference grass crop (dimensionless).
# FAO-56 Table 3.2 suggests 0.23.
DEFAULT_ALBEDO = 0.23

"""NASA POWER daily parameters used for minimal ET computations.

Includes: T2M_MAX, T2M_MIN (°C), RH2M (%), WS10M (m/s),
ALLSKY_SFC_SW_DWN (MJ m⁻²), PRECTOTCORR (mm).
Ref: NASA POWER Daily Parameters:
https://power.larc.nasa.gov/docs/services/api/temporal/daily/parameters/
"""
POWER_DAILY_PARAMS_MINIMAL = "T2M_MAX,T2M_MIN,RH2M,WS10M,ALLSKY_SFC_SW_DWN,PRECTOTCORR"

# FAO-56 saturation vapour pressure (Tetens) constants (Eq. 11):
FAO_SVP_A_KPA = 0.6108  # kPa - base coefficient in e_s(T)
FAO_SVP_B = 17.27  # dimensionless - exponential numerator coefficient
FAO_SVP_C = 237.3  # °C - exponential denominator offset

"""Psychrometric/pressure constants (FAO-56 Eq. 7–8).

Atmospheric pressure as a function of elevation (z, m):
  P(kPa) = 101.3 * ((293 - 0.0065*z) / 293) ^ 5.26
Psychrometric constant:
  γ (kPa/°C) = 0.000665 * P(kPa)
"""
SEA_LEVEL_PRESSURE_KPA = 101.3  # kPa - standard sea level pressure
PRESSURE_TEMP_REF_K = 293.0  # K   - reference temperature in pressure equation
LAPSE_RATE_K_PER_M = 0.0065  # K/m - standard atmosphere lapse rate
PRESSURE_EXPONENT = 5.26  # dimensionless - pressure-elevation exponent
PSYCHROMETRIC_COEFF_PER_KPA = 0.000665  # kPa/°C per kPa of atmospheric pressure

"""Other ET constants (FAO-56):
- LATENT_HEAT_MJ_PER_KG: latent heat of vaporization of water (~2.45 MJ/kg at ~20 °C)
  used to convert available energy (MJ m⁻² d⁻¹) to equivalent water depth (mm d⁻¹).
  FAO-56 commonly treats this as constant; more precise formulations use
  lambda [MJ kg⁻¹] ≈ 2.501 − 0.002361·T(°C).
- DELTA_NUMERATOR: 4098 in slope of saturation vapour pressure curve
  calculation (Eq. 13)
- PSYCHROMETRIC_CONST_APPROX_KPA_PER_C: 0.067 kPa/°C – often used where
  site-specific pressure is unavailable
- FAO_PM_NUMERATOR_COEF: 900 for daily time step in Penman–Monteith equation (Eq. 6)
- ABSOLUTE_ZERO_C: 273 to convert °C to Kelvin in FAO-56 formulations
"""
LATENT_HEAT_MJ_PER_KG = 2.45  # MJ/kg
DELTA_NUMERATOR = 4098.0  # dimensionless
PSYCHROMETRIC_CONST_APPROX_KPA_PER_C = 0.067  # kPa/°C
FAO_PM_NUMERATOR_COEF = 900.0  # dimensionless (daily time step)
ABSOLUTE_ZERO_C = 273.0  # °C

# Solar declination constant for photoperiod (Spencer 1971).
# Maximum declination in radians (~23.44°).
EARTH_AXIAL_TILT_RAD = 0.4093
