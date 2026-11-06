import { browser } from '$app/environment';
import { replaceState } from '$app/navigation';

/**
 * Centralized serialization and parsing of shareable URL state.
 *
 * These are pure functions with no Svelte or DOM dependencies, so the query
 * string contract for shareable links stays in one place and is easy to test.
 *
 * Trip params: `from` and `to` are "lat,lng" strings; `fromName` and `toName`
 * are optional human readable labels.
 */

/** Number of decimal places kept for coordinates (about 1 meter precision). */
const COORD_PRECISION = 5;

/**
 * Rounds a coordinate pair and renders it as a compact "lat,lng" string.
 *
 * @param {{ lat: number, lng: number } | null | undefined} coords
 * @returns {string | null} The "lat,lng" string, or null if coords are invalid
 */
export function formatCoord(coords) {
	if (!coords) return null;
	const { lat, lng } = coords;
	if (!isValidLat(lat) || !isValidLng(lng)) return null;
	return `${round(lat)},${round(lng)}`;
}

/**
 * Parses a "lat,lng" string into a validated coordinate object.
 *
 * @param {string | null | undefined} value
 * @returns {{ lat: number, lng: number } | null} The coordinates, or null if invalid
 */
export function parseCoord(value) {
	if (!value || typeof value !== 'string') return null;

	const parts = value.split(',');
	if (parts.length !== 2) return null;

	const [latStr, lngStr] = parts.map((p) => p.trim());
	if (latStr === '' || lngStr === '') return null;

	// Number() (unlike parseFloat) rejects trailing garbage such as "47.6xyz"
	// instead of silently truncating it to a plausible-looking coordinate.
	const lat = Number(latStr);
	const lng = Number(lngStr);

	if (!isValidLat(lat) || !isValidLng(lng)) return null;

	return { lat, lng };
}

/**
 * Returns true when the URL has an attempt at trip params (`from` or `to`
 * present), regardless of whether they parse successfully. Lets callers
 * distinguish "no shared trip" from "a shared trip link that didn't parse" so
 * a broken link can surface feedback instead of silently falling back to the
 * default map with no explanation.
 *
 * @param {URLSearchParams} searchParams
 * @returns {boolean}
 */
export function hasTripParams(searchParams) {
	if (!searchParams) return false;
	return searchParams.has('from') || searchParams.has('to');
}

/**
 * Parse an optional Israel-local departure/arrival time from shared links.
 * Two accepted forms:
 *   date=2026-11-08&time=09:30
 *   departAt=2026-11-08T09:30
 * Optional arriveBy=true|false|1|0 changes departure to arrival search.
 * These are LOCAL Asia/Jerusalem wall-clock values, not UTC instants.
 *
 * @param {URLSearchParams} params
 * @returns {{departureType: 'departAt'|'arriveBy',departureDate:string,departureTime:string} | undefined | null}
 *   undefined: no schedule supplied; null: supplied but invalid.
 */
export function parseTripScheduleParams(params) {
	if (!params) return undefined;
	const hasSchedule = ['date', 'time', 'departAt', 'arriveBy'].some((name) => params.has(name));
	if (!hasSchedule) return undefined;
	const shortcut = params.get('departAt');
	if (shortcut !== null && (params.has('date') || params.has('time'))) return null;
	const match = shortcut !== null ? /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})$/.exec(shortcut) : null;
	if (shortcut !== null && !match) return null;
	const date = match ? match[1] : params.get('date');
	const time = match ? match[2] : params.get('time');
	if (
		!date ||
		!time ||
		!/^\d{4}-\d{2}-\d{2}$/.test(date) ||
		!/^([01]\d|2[0-3]):[0-5]\d$/.test(time)
	)
		return null;
	const [year, month, day] = date.split('-').map(Number);
	if (
		year < 2000 ||
		year > 2100 ||
		month < 1 ||
		month > 12 ||
		day < 1 ||
		day > new Date(Date.UTC(year, month, 0)).getUTCDate()
	)
		return null;
	const rawArrive = params.get('arriveBy');
	if (rawArrive !== null && !['0', '1', 'true', 'false'].includes(rawArrive)) return null;
	return {
		departureType: rawArrive === '1' || rawArrive === 'true' ? 'arriveBy' : 'departAt',
		departureDate: date,
		departureTime: time
	};
}

/**
 * Reads trip context from URL search params.
 *
 * @param {URLSearchParams} searchParams
 * @returns {{ selectedFrom: { lat: number, lng: number }, selectedTo: { lat: number, lng: number }, fromPlace: string, toPlace: string } | null}
 *          The restored trip, or null when from/to are missing or invalid
 */
export function parseTripParams(searchParams) {
	if (!searchParams) return null;

	const selectedFrom = parseCoord(searchParams.get('from'));
	const selectedTo = parseCoord(searchParams.get('to'));

	if (!selectedFrom || !selectedTo) return null;
	const schedule = parseTripScheduleParams(searchParams);
	if (schedule === null) return null;

	const fromName = searchParams.get('fromName');
	const toName = searchParams.get('toName');

	return {
		selectedFrom,
		selectedTo,
		fromPlace: fromName || formatCoord(selectedFrom),
		toPlace: toName || formatCoord(selectedTo),
		...(schedule || {})
	};
}

/**
 * Writes trip context onto a URL's search params in place. Skips writing when
 * either coordinate is invalid so a broken link is never produced.
 *
 * @param {URL} url - URL whose searchParams will be mutated
 * @param {{ selectedFrom: object, selectedTo: object, fromPlace?: string, toPlace?: string }} trip
 * @returns {URL} The same url, for chaining
 */
export function applyTripParams(url, trip) {
	const from = formatCoord(trip?.selectedFrom);
	const to = formatCoord(trip?.selectedTo);

	if (!from || !to) return url;

	url.searchParams.set('from', from);
	url.searchParams.set('to', to);

	if (trip.fromPlace) {
		url.searchParams.set('fromName', trip.fromPlace);
	} else {
		url.searchParams.delete('fromName');
	}

	if (trip.toPlace) {
		url.searchParams.set('toName', trip.toPlace);
	} else {
		url.searchParams.delete('toName');
	}

	// Avoid stale timestamps when sharing "leave now" or replanning after a
	// previous scheduled journey. Only keep a fully valid schedule.
	for (const name of ['date', 'time', 'departAt', 'arriveBy']) url.searchParams.delete(name);
	const kind = trip.departureType;
	if (kind === 'departAt' || kind === 'arriveBy') {
		const schedule = parseTripScheduleParams(
			new URLSearchParams({
				date: trip.departureDate || '',
				time: trip.departureTime || '',
				arriveBy: kind === 'arriveBy' ? 'true' : 'false'
			})
		);
		if (schedule) {
			url.searchParams.set('date', schedule.departureDate);
			url.searchParams.set('time', schedule.departureTime);
			if (kind === 'arriveBy') url.searchParams.set('arriveBy', 'true');
		}
	}
	return url;
}

/**
 * Removes all trip params from a URL's search params in place.
 *
 * @param {URL} url - URL whose searchParams will be mutated
 * @returns {URL} The same url, for chaining
 */
export function removeTripParams(url) {
	url.searchParams.delete('from');
	url.searchParams.delete('to');
	url.searchParams.delete('fromName');
	url.searchParams.delete('toName');
	for (const name of ['date', 'time', 'departAt', 'arriveBy']) url.searchParams.delete(name);
	return url;
}

/**
 * Clears shareable trip parameters from the current URL in place via replaceState.
 *
 * @param {URL | string} [url] - Optional URL to clear. Defaults to window.location.href
 */
export function clearTripUrl(url) {
	if (!browser) return;
	try {
		const base = url || window?.location?.href;
		if (!base) return;
		const parsedUrl = new URL(base);
		removeTripParams(parsedUrl);
		// using `resolve` would drop trip params
		// eslint-disable-next-line svelte/no-navigation-without-resolve
		replaceState(parsedUrl, {});
	} catch (e) {
		console.warn('Failed to clear shareable trip URL:', e);
	}
}

function round(value) {
	return Number(value.toFixed(COORD_PRECISION));
}

function isValidLat(lat) {
	return typeof lat === 'number' && isFinite(lat) && lat >= -90 && lat <= 90;
}

function isValidLng(lng) {
	return typeof lng === 'number' && isFinite(lng) && lng >= -180 && lng <= 180;
}
