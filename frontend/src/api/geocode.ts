interface NominatimAddress {
  city?: string;
  town?: string;
  village?: string;
  municipality?: string;
  county?: string;
  state?: string;
  country?: string;
}

interface NominatimResponse {
  address?: NominatimAddress;
  display_name?: string;
}

/**
 * Client-side reverse geocoding via Nominatim (OpenStreetMap, free). Called
 * only when the user explicitly shares their location, so volume is
 * naturally low — fine under Nominatim's usage policy without a backend
 * proxy or API key. Returns null (never throws) if the lookup fails, so a
 * geocoding hiccup never blocks saving the actual coordinates.
 */
export async function reverseGeocode(
  lat: number,
  lon: number,
): Promise<string | null> {
  try {
    const response = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}&zoom=10&addressdetails=1&accept-language=en`,
    );
    if (!response.ok) return null;
    const data: NominatimResponse = await response.json();
    const address = data.address;
    if (!address) return data.display_name ?? null;

    const place =
      address.city ??
      address.town ??
      address.village ??
      address.municipality ??
      address.county ??
      address.state;

    if (place && address.country) return `${place}, ${address.country}`;
    return place ?? address.country ?? data.display_name ?? null;
  } catch {
    return null;
  }
}
