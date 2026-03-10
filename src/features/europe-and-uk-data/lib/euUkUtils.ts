/**
 * Utility helpers for EU / UK regulatory data.
 */

/** Build a link to the EUDAMED device record for a given Basic UDI-DI */
export function eudamedUrl(basicUdi: string): string {
  return `https://ec.europa.eu/tools/eudamed/#/screen/search-device?basicUdi=${encodeURIComponent(basicUdi)}`;
}

/** Build a link to the HC MDALL record for a given licence number */
export function mdallUrl(licenceNo: string): string {
  return `https://health-products.canada.ca/mdall-limh/deviceid-idproduit/${licenceNo}`;
}

/** Risklass code → human label */
export function euRiskClassLabel(code: string): string {
  const map: Record<string, string> = {
    "refdata.risk-class.class-i":   "Class I",
    "refdata.risk-class.class-iia": "Class IIa",
    "refdata.risk-class.class-iib": "Class IIb",
    "refdata.risk-class.class-iii": "Class III",
    "refdata.risk-class.class-a":   "Class A (IVD)",
    "refdata.risk-class.class-b":   "Class B (IVD)",
    "refdata.risk-class.class-c":   "Class C (IVD)",
    "refdata.risk-class.class-d":   "Class D (IVD)",
  };
  return map[code] ?? code;
}

/** Countries where this approval applies */
export const EU_MEMBER_STATES = [
  "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic",
  "Denmark", "Estonia", "Finland", "France", "Germany", "Greece", "Hungary",
  "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta",
  "Netherlands", "Poland", "Portugal", "Romania", "Slovakia", "Slovenia",
  "Spain", "Sweden",
];
