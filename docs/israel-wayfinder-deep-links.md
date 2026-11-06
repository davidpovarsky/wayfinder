# Wayfinder Israel: agent and Telegram deep links

Use the HTTPS origin \`https://wayfinder-130-110-238-163.nip.io/\`.
Comma agents can send a regular clickable URL. Opening a native Telegram
\`web_app\` button requires Telegram connector support and a user tap; do not
claim Comma supports that when it exposes text links only.

## Journey plan (Israel local wall clock)

\`\`\`
?from=31.816586,35.202785&to=31.788564,35.224251&date=2026-11-08&time=09:30
\`\`\`

- \`from\` / \`to\`: \`latitude,longitude\`. Both are required to plan.
- \`date\`: \`YYYY-MM-DD\` valid calendar date.
- \`time\`: \`HH:mm\` 24-hour local time in **Asia/Jerusalem** (not UTC).
- Alternative shortcut: \`departAt=2026-11-08T09:30\` instead of both
  \`date\` and \`time\` (must NOT use with either of them).
- \`arriveBy=true\`: search to **arrive** by the specified local time;
  omit for departure search. Supported with either date/time form.
- \`fromName\` / \`toName\`: optional percent-encoded human-readable labels.
- Do not attach a timezone offset or \`Z\` to date/time or departAt; links
  with malformed/ambiguous schedule values are rejected.
- All old links with only \`from\`/\`to\` still work and plan as "leave now".
- An empty planner remains \`?plan=1\`.
- The app normalizes successful shared itineraries to \`date\` and \`time\`
  in its own share URL and drops a stale schedule for "leave now" trips.

## More screens

- Route (use *actual numeric MOT routeId*, not public line number):
  \`?route=33285\` -> bus line 31 (one specified direction)
- Stop: \`/map/stops/mot%3Astop%3A5997\`
- Map center: \`?lat=31.815188&lng=35.203022\`

## Requirements for agents

1. Resolve actual locations/route IDs using the transport skill first.
2. Encode query parameters as URL parameters. Do not invent a coordinate.
3. Supply the requested local calendar date and 24-hour wall clock; when
   the user did not specify timing, leave date/time/arriveBy out entirely.
4. If the user says "arrive by", append \`arriveBy=true\`.
5. Link opens the app UI, which asks the Ministry of Transport for real
   itineraries; never claim any itinerary was verified from a link alone.
6. If a user's browser cannot access MOT live data, a link will not
   manufacture bus routes or departure times.

Example (home -> Mir on Nov 8, 2026 at 09:30 Israel time):
\`https://wayfinder-130-110-238-163.nip.io/?from=31.816586%2C35.202785&to=31.788564%2C35.224251&date=2026-11-08&time=09%3A30\`
