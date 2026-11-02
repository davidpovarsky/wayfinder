# Wayfinder Israel — MOT Compatibility

This fork keeps upstream Wayfinder's SvelteKit UI and maps real Israeli Ministry
of Transport data to the OneBusAway REST v2 contract. The compatibility layer
is based on `davidpovarsky/onebusaway-ios` branch
`fix/israel-extraction-and-repair-20261027`, notably its
`MOTCompatibilityDataLoader`, `OBACompatibilityBridge`,
`MOTItineraryMapper`, and `IsraelStopCatalog.sqlite`.

## Start locally (Windows)

```powershell
cd C:\Users\DAVID\Code\wayfinder
npm install
python israel-compat\server.py
# in a second terminal
npm run dev -- --host 127.0.0.1
```

The `.env` file (not committed) points the SDK to
`http://127.0.0.1:8770`. To regenerate it use `.env.example`
and set:

```dotenv
PUBLIC_OBA_SERVER_URL="http://127.0.0.1:8770"
PRIVATE_OBA_API_KEY="test"
PUBLIC_OBA_REGION_CENTER_LAT=31.78913
PUBLIC_OBA_REGION_CENTER_LNG=35.20317
PUBLIC_OBA_REGION_NAME="ישראל"
PUBLIC_OBA_TIMEZONE="Asia/Jerusalem"
PUBLIC_OBA_MAP_PROVIDER="osm"
PUBLIC_DEFAULT_LOCALE="he"
PUBLIC_MAPBOX_TOKEN=""  # optional public pk. token
```

Mapbox is optional: when a valid public `pk.` token is configured,
the existing MapLibre/Leaflet map uses Mapbox Streets/ Dark styles.
If empty, existing OpenFreeMap styling remains in place. Never set a
secret `sk.` token in a public environment variable.

## What's implemented

- OneBusAway API v2 envelopes, agency coverage and observed route index
- National Israeli stop catalogue with R-Tree spatial search
- Live stop information, stop routes, real timetable data only when supplied
- Route stops and HERE flexible polyline -> Google E5 map geometry
- Live query for route numbers through MOT AutoComplete/SearchLines
- OTP REST planning bridge using the original iOS request/response mapping
- Hebrew translations, RTL, and optional Mapbox styling
- Fail-closed outages: no fake arrival predictions or routes

## Known limitations

- MOT may return 403/429/503 and requests can fail even with standard
  browser headers. No bypass of provider authorization or rate limits.
- The original MOT `StopFullData` often returns zero arrivals; the app
  displays the absence instead of invented ETAs.
- Complete national route index and all providers are not yet sourced.
  The startup index is seeded from observed routes at a real stop.
- OTP route planning is dependent on the external MOT planner; the 503
  response is explicitly surfaced. Conversion is tested against the user's
  captured real planner fixtures but doesn't guarantee future availability.
- Vehicle positions and alerts are not fully mapped. These are not faked.
- Development currently runs on a private loopback endpoint. Production
  exposure/Telegram should only be enabled after authentication is configured.

## Tests

```powershell
cd israel-compat
python -m unittest discover -s tests -p test_server.py -v
node tests/sdk-smoke.mjs
cd ..
npm run check
npm run build
```

## License

Wayfinder remains AGPL-3.0. Follow the network-source availability obligations
when exposing a modified deployment. The source iOS code was Apache-2.0;
metadata/licensing of the GTFS-MOT station data must be respected separately.
