// Only contact the installed MOT service on private loopback.
import { PUBLIC_OBA_SERVER_URL, PUBLIC_OBA_REGION_NAME } from '$env/static/public';
export function isIsraelTransit() {
    return PUBLIC_OBA_REGION_NAME === 'ישראל';
}
export async function getIsraelPlaces(query) {
    const term = String(query || '').trim().slice(0, 120);
    if (term.length < 2) return { suggestions: [], location: null };
    const host = new URL(PUBLIC_OBA_SERVER_URL);
    if (!['127.0.0.1', 'localhost', '::1'].includes(host.hostname)) {
        throw new Error('Israeli geocoder must run on server loopback');
    }
    const url = new URL('/geo/search', host);
    url.searchParams.set('query', term);
    const response = await fetch(url, { signal: AbortSignal.timeout(13000) });
    if (!response.ok) throw new Error('MOT geocoder returned HTTP ' + response.status);
    const body = await response.json();
    return { suggestions: Array.isArray(body.suggestions) ? body.suggestions : [],
             location: body.location || null };
}
