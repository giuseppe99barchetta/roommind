/** Far-future sentinel timestamp (year 3000): vacation active indefinitely. */
export const VACATION_SENTINEL = 32503680000;

/** CO2 threshold in ppm and its bounds; mirror DEFAULT/MIN/MAX_CO2_THRESHOLD in const.py (#267). */
export const DEFAULT_CO2_THRESHOLD = 1000;
export const MIN_CO2_THRESHOLD = 800;
export const MAX_CO2_THRESHOLD = 5000;

/** Slider default; mirrors DEFAULT_COMFORT_WEIGHT. At and above it pre-heating is not limited. */
export const DEFAULT_COMFORT_WEIGHT = 70;
/** Longest pre-heat lead; mirrors PREHEAT_MAX_LEAD_HOURS (mpc_optimizer). */
export const PREHEAT_MAX_LEAD_HOURS = 12;

/**
 * Pre-heat lead in hours the slider allows; mirrors preheat_max_blocks() (5-min blocks): null
 * from the default weight up, where the optimizer plans as far as its horizon reaches.
 */
export function preheatLeadHours(comfortWeight: number): number | null {
  if (comfortWeight >= DEFAULT_COMFORT_WEIGHT) return null;
  const hours = (PREHEAT_MAX_LEAD_HOURS * Math.max(comfortWeight, 0)) / DEFAULT_COMFORT_WEIGHT;
  return (Math.floor((hours * 60) / 5) * 5) / 60;
}
