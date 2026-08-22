const EARTH_RADIUS_KM = 6371;

const toCoordinate = (value) => {
  if (value == null || value === '') return null;
  const coordinate = Number(value);
  return Number.isFinite(coordinate) ? coordinate : null;
};

const readCoordinates = (source, latKeys, lngKeys) => {
  for (let index = 0; index < latKeys.length; index += 1) {
    const lat = toCoordinate(source?.[latKeys[index]]);
    const lng = toCoordinate(source?.[lngKeys[index]]);
    if (lat != null && lng != null) return { lat, lng };
  }
  return null;
};

const toRadians = (value) => (value * Math.PI) / 180;

const isAgencyActive = (agency) => {
  const value = agency?.agency_is_active;
  const normalizedValue = typeof value === 'string' ? value.toLowerCase() : value;
  return ![false, 0, '0', 'false'].includes(normalizedValue);
};

export const distanceKmBetween = (from, to) => {
  const latitudeDelta = toRadians(to.lat - from.lat);
  const longitudeDelta = toRadians(to.lng - from.lng);
  const fromLatitude = toRadians(from.lat);
  const toLatitude = toRadians(to.lat);
  const haversine = (
    Math.sin(latitudeDelta / 2) ** 2
    + Math.cos(fromLatitude) * Math.cos(toLatitude) * Math.sin(longitudeDelta / 2) ** 2
  );

  return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine));
};

export const findNearestAgency = (location, agencies = []) => {
  const locationCoordinates = readCoordinates(
    location,
    ['cctv_lat', 'lat', 'latitude'],
    ['cctv_lng', 'lng', 'longitude'],
  );
  if (!locationCoordinates || !Array.isArray(agencies)) return null;

  return agencies
    .filter(isAgencyActive)
    .map((agency) => {
      const agencyCoordinates = readCoordinates(
        agency,
        ['agency_lat', 'lat', 'latitude'],
        ['agency_lng', 'lng', 'longitude'],
      );
      if (!agencyCoordinates) return null;

      return {
        ...agency,
        distance_km: distanceKmBetween(locationCoordinates, agencyCoordinates),
      };
    })
    .filter(Boolean)
    .sort((left, right) => {
      const distanceDifference = left.distance_km - right.distance_km;
      if (distanceDifference !== 0) return distanceDifference;
      return Number(left.agency_no || 0) - Number(right.agency_no || 0);
    })[0] || null;
};
