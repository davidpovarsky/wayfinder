// @ts-check
import { json } from '@sveltejs/kit';
import { fetchAutocompleteResults } from '$lib/geocoder';
import { getBoundsCache } from '$lib/serverCache.js';
import { getIsraelPlaces, isIsraelTransit } from '$lib/server/israelGeocoder';

import { PRIVATE_OBA_GEOCODER_PROVIDER as geocoderProvider } from '$env/static/private';

import { env } from '$env/dynamic/private';

let geocoderApiKey = env.PRIVATE_OBA_GEOCODER_API_KEY;

/** @param {import('@sveltejs/kit').RequestEvent} event */
export async function GET({ url }) {
	const searchInput = url.searchParams.get('query')?.trim() ?? '';

	const bounds = getBoundsCache();

	let suggestions;
	try {
		suggestions = isIsraelTransit() && !geocoderApiKey
			? (await getIsraelPlaces(searchInput)).suggestions
			: !geocoderApiKey ? [] : await fetchAutocompleteResults(
				geocoderProvider, searchInput, geocoderApiKey, bounds
			);
	} catch (err) {
		console.error('Place suggestion provider unavailable:', err);
		return json({ suggestions: [], error: 'ADDRESS_LOOKUP_UNAVAILABLE' }, { status: 503 });
	}

	/** @type {import('$lib/types').PlaceSuggestionsResponse} */
	const body = { suggestions };
	return json(body);
}
