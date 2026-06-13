/**
 * 2-digit state FIPS code → 2-letter USPS postal abbreviation, for the
 * 50 states + DC (and DC's territories where the county/tract maps
 * carry data). Used to suffix county/tract hover labels with the state
 * so "Travis" reads "Travis, TX" — disambiguating the dozens of
 * same-named counties across states and orienting the reader.
 *
 * Postal codes (not "County"/"Parish"/"Borough") are appended on hover
 * precisely because the local-government noun varies (LA parishes, AK
 * boroughs, independent cities), while ", TX" is always correct.
 */
export const STATE_FIPS_TO_POSTAL: Readonly<Record<string, string>> = {
  "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
  "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
  "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
  "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
  "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
  "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
  "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
  "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
  "54": "WV", "55": "WI", "56": "WY",
  // Territories that appear in some Census files.
  "60": "AS", "66": "GU", "69": "MP", "72": "PR", "78": "VI",
};

/** Postal code for a 2-digit state FIPS prefix, or "" if unknown. */
export function statePostalFromFips(fips2: string): string {
  return STATE_FIPS_TO_POSTAL[fips2] ?? "";
}
