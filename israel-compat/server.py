"""Israel MOT -> OneBusAway v2 REST compatibility server for Wayfinder.

Uses the real Israeli stop catalogue from the user's iOS fork and real MOT API
responses. Never invents arrivals, route times, vehicles or trip itineraries.
Binds to loopback only; Wayfinder's server talks to it on the same machine.
"""
from __future__ import annotations

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo
import json
import otp_adapter
import math
import os
import re
import sqlite3
import threading
import time

BASE = Path(__file__).parent
CATALOG = Path(os.environ.get("ISRAEL_STOPS_DB", str(BASE / "data" / "IsraelStopCatalog.sqlite")))
HOST = os.environ.get("ISRAEL_OBA_HOST", "127.0.0.1")
PORT = int(os.environ.get("ISRAEL_OBA_PORT", "8770"))
SCHEDULER = "https://api.bus.gov.il/prod/mot-scheduler-prod/api/he/"
PLANNER = "https://api.bus.gov.il/prod/route-planner-prod/api/he/"
try:
    ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")
except Exception:
    # Windows Python may lack a bundled IANA timezone database.
    # Use the machine timezone for local development; install tzdata in production.
    ISRAEL_TZ = datetime.now().astimezone().tzinfo
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://bus.gov.il",
    "Referer": "https://bus.gov.il/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
}
_cache = {}
_lock = threading.RLock()


def ms() -> int:
    return int(time.time() * 1000)


def envelope(data, code=200, text="OK"):
    return {"code": code, "currentTime": ms(), "text": text, "version": 2, "data": data}


def refs(stops=(), routes=(), agencies=(), trips=()):
    return {"stops": list(stops), "routes": list(routes), "agencies": list(agencies),
            "trips": list(trips), "situations": []}


def name(x):
    if isinstance(x, dict):
        return x.get("he") or x.get("en") or ""
    return str(x or "")


def stop_id(code, internal=None):
    return "mot:stop:" + str(code) + (":" + str(internal) if internal else "")


def stop_code(scoped):
    match = re.search(r"(?:mot:stop:)?([0-9]+)", str(scoped))
    return int(match.group(1)) if match else None


def route_id(x):
    match = re.search(r"(?:mot:(?:route|shape|trip):)?([0-9]+)", str(x))
    return int(match.group(1)) if match else None


def agency(x=1, agency_name=None):
    return {"id": "mot:agency:" + str(x or 1), "name": agency_name or "משרד התחבורה",
            "url": "", "timezone": "Asia/Jerusalem", "lang": "he", "phone": "",
            "privateService": False}


def route_summary(r):
    rid = r.get("routeId")
    aid = r.get("agencyId") or 1
    line = str(r.get("routeName") or "")
    dest = name(r.get("headsign")) or str(r.get("routeLongName") or "").split("<->")[-1]
    return {"id": f"mot:route:{rid}", "agencyId": f"mot:agency:{aid}",
            "shortName": line, "longName": dest, "description": str(r.get("routeDesc") or ""),
            "type": 3, "url": "", "color": "2072B8", "textColor": "FFFFFF"}


def serialize_stop(s, requested=None):
    code = s.get("stopcode") or s.get("stop_code") or s.get("stopCode")
    sid = s.get("stopid") or s.get("stop_id")
    routes = s.get("routesInStop") or []
    result = {"id": requested or stop_id(code, sid), "code": str(code or ""),
              "name": name(s.get("name")) or s.get("name_he") or "",
              "lat": float(s.get("lat", 0)), "lon": float(s.get("lng", s.get("lon", 0))),
              "direction": "", "locationType": 0, "routeIds": [
                f"mot:route:{r['routeId']}" for r in routes if r.get("routeId")],
              "wheelchairBoarding": "UNKNOWN", "platformCode": str(s.get("platformNumber") or s.get("platform_code") or "")}
    return result


def db():
    if not CATALOG.exists():
        raise FileNotFoundError(f"Catalog missing: {CATALOG}")
    con = sqlite3.connect(str(CATALOG), timeout=8)
    con.row_factory = sqlite3.Row
    return con


def query_stops(lat=None, lon=None, lat_span=0.02, lon_span=0.02, search="", limit=100):
    limit = max(1, min(250, int(limit)))
    with db() as conn:
        if search.strip():
            q = "%" + search.strip().replace("%", r"\%").replace("_", r"\_") + "%"
            rows = conn.execute(
                "SELECT * FROM stops WHERE name_he LIKE ? ESCAPE '\\' OR city LIKE ? ESCAPE '\\' OR CAST(stop_code AS TEXT)=? LIMIT ?",
                (q, q, search.strip(), limit)).fetchall()
        else:
            lat, lon = float(lat or 31.78), float(lon or 35.21)
            lat_span = max(0.002, min(1.2, float(lat_span)))
            lon_span = max(0.002, min(1.2, float(lon_span)))
            rows = conn.execute(
                "SELECT s.* FROM stops_rtree r JOIN stops s ON s.stop_id=r.id "
                "WHERE r.min_lat<=? AND r.max_lat>=? AND r.min_lon<=? AND r.max_lon>=? "
                "ORDER BY (s.lat-?)*(s.lat-?)+(s.lon-?)*(s.lon-?) LIMIT ?",
                (lat+lat_span/2, lat-lat_span/2, lon+lon_span/2, lon-lon_span/2,
                 lat, lat, lon, lon, limit)).fetchall()
        return [dict(r) for r in rows]


def lookup_stop(code):
    with db() as conn:
        row = conn.execute("SELECT * FROM stops WHERE stop_code=? LIMIT 1", (code,)).fetchone()
        return dict(row) if row else None


def fetch_mot(which, endpoint, params=None, body=None, ttl=25):
    """Bounded trusted-origin API client. Distinguishes remote outage from no data."""
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    base = SCHEDULER if which == "scheduler" else PLANNER
    url = base + endpoint + ("?" + urlencode(params) if params else "")
    key = (which, endpoint, json.dumps(params, sort_keys=True), json.dumps(body, sort_keys=True))
    with _lock:
        item = _cache.get(key)
        if item and item[0] > time.time():
            return item[1]
    headers = dict(HEADERS)
    data = json.dumps(body).encode() if body is not None else None
    if data:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urlopen(request, timeout=13) as response:
            if response.status != 200:
                raise MOTUnavailable(f"MOT HTTP {response.status}")
            payload = json.load(response)
            if not payload.get("success", False):
                raise MOTUnavailable(str(payload.get("message") or "MOT reported failure")[:200])
            result = payload.get("data")
            with _lock:
                if len(_cache) > 2000:
                    _cache.clear()
                _cache[key] = (time.time() + ttl, result)
            return result
    except HTTPError as exc:
        raise MOTUnavailable(f"MOT HTTP {exc.code}") from None
    except (URLError, TimeoutError, ValueError) as exc:
        raise MOTUnavailable(f"MOT unavailable: {type(exc).__name__}") from None


class MOTUnavailable(Exception):
    pass


def stop_details(code):
    return fetch_mot("scheduler", "Stops/GetStopFullData", {"stopCode": code}, ttl=40)


def route_details(rid):
    return fetch_mot("scheduler", "Routes/GetRouteFullData", {"routeId": rid}, ttl=300)


def stop_and_routes(code, requested=None):
    local = lookup_stop(code)
    if not local:
        return None, [], []
    try:
        live = stop_details(code)
        live = live if isinstance(live, dict) else {}
    except MOTUnavailable:
        live = {}
    merged = dict(local)
    merged.update({k:v for k,v in live.items() if v is not None})
    routes = [route_summary(x) for x in live.get("routesInStop", []) if x.get("routeId")]
    agencies = list({x["id"]: x for x in [agency(r.get("agencyId"), r.get("agencyName")) for r in live.get("routesInStop", [])]}.values())
    return serialize_stop(merged, requested), routes, agencies


def fetch_next_stop_times(live, code):
    """Reuse iOS MOTCompatibilityDataLoader's per-route POST strategy.

    HTTP responses are real, cached for 20 seconds, and bounded at four
    concurrent requests. Missing/blocked routes produce no invented ETAs.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    routes = [r for r in live.get("routesInStop",[]) if r.get("routeDesc") and r.get("routeId")]
    dedup = list({r["routeDesc"]:r for r in routes}.values())[:50]

    def fetch_route(route):
        desc=route["routeDesc"]
        try:
            data = fetch_mot("scheduler", "Routes/GetNextStopTimesAndLocation",
                             body={"routeDesc":desc,"stopCodes":[int(code)]},ttl=20)
            times=(data or {}).get(str(code)) or {}
            out = []
            for item in times.get("stopTimes") or []:
                out.append({**item,"routeId":route["routeId"],"routeName":route.get("routeName"),
                            "headsign":route.get("headsign") or route.get("routeLongName")})
            return out
        except (MOTUnavailable,AttributeError,ValueError,TypeError):
            return []

    if not dedup: return []
    collected=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(fetch_route,r) for r in dedup]):
            try:collected.extend(future.result())
            except Exception:pass
    return collected


def get_arrivals(live, stop_code_number, stop_identifier, min_before=0, min_after=60):
    """Use only genuine time fields; missing real-time data is not an ETA."""
    values, trips = [], {}
    current = ms()
    raw = list(live.get("stopTimes") or [])
    for route in live.get("routesInStop") or []:
        rid = route.get("routeId")
        for s in route.get("stops") or []:
            if int(s.get("stopcode") or 0) != int(stop_code_number):
                continue
            for it in (s.get("nextStopsTimes") or []):
                raw.append({**it, "routeId": rid, "routeName": route.get("routeName"),
                            "headsign": route.get("headsign") or route.get("routeLongName")})
    for index, a in enumerate(raw):
        try:
            rid = int(a.get("routeId") or 0)
            if not rid: continue
            raw_time = a.get("arrivalTime") or a.get("staticArrivalTime")
            if not raw_time: continue
            when = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=ISRAEL_TZ)
            scheduled = int(when.timestamp()*1000)
            if not current - min_before*60000 <= scheduled <= current + min_after*60000:
                continue
            r_id = f"mot:route:{rid}"
            trip_id = "mot:trip:" + str(rid) + ":" + str(a.get("staticTripId") or a.get("tripIdToDate") or scheduled)
            dest = name(a.get("headsign"))
            trip = {"id": trip_id, "routeId": r_id, "serviceId": "mot:service:default",
                    "tripHeadsign": dest, "routeShortName": str(a.get("routeName") or ""),
                    "shapeId": f"mot:shape:{rid}", "directionId": "0", "timeZone": "Asia/Jerusalem"}
            trips[trip_id] = trip
            predicted = bool(a.get("isRealTime"))
            arrival = {"routeId": r_id, "routeShortName": str(a.get("routeName") or ""),
                       "routeLongName": dest, "tripId": trip_id, "tripHeadsign": dest,
                       "stopId": stop_identifier, "stopSequence": int(a.get("stopOrder") or 1),
                       "scheduledArrivalTime": scheduled, "scheduledDepartureTime": scheduled,
                       "predicted": predicted, "lastUpdateTime": current,
                       "serviceDate": int(when.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()*1000),
                       "vehicleId": "", "distanceFromStop": -1, "numberOfStopsAway": -1,
                       "status": "default" if predicted else "scheduled",
                       "arrivalEnabled": True, "departureEnabled": True, "situationIds": []}
            if predicted and a.get("minutesToArrival") is not None:
                p = current + int(float(a["minutesToArrival"])*60000)
                arrival.update(predictedArrivalTime=p, predictedDepartureTime=p)
            values.append(arrival)
        except (TypeError, ValueError, OverflowError):
            continue
    values.sort(key=lambda x: x.get("predictedArrivalTime", x["scheduledArrivalTime"]))
    return values, list(trips.values())


ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def decode_here_polyline(value):
    """Decode HERE flexible polyline v1; return [[lat,lon],...]."""
    if not value or len(value) > 150000: return []
    nums = []
    acc = 0
    shift = 0
    for char in value:
        v = ALPHABET.find(char)
        if v == -1: return []
        acc |= (v & 31) << shift
        if v & 32:
            shift += 5
            if shift > 60: return []
        else:
            nums.append(acc)
            acc = 0
            shift = 0
    if len(nums) < 2 or nums[0] != 1: return []
    precision = nums[1] & 15
    third_dim = (nums[1] >> 4) & 7
    third_precision = (nums[1] >> 7) & 15
    if third_dim not in (0, 1, 2, 3, 6, 7): return []
    factor = 10 ** precision
    step = 3 if third_dim else 2
    lat = lng = 0
    points = []
    for i in range(2, len(nums)-step+1, step):
        dlat = (nums[i] >> 1) ^ -(nums[i] & 1)
        dlng = (nums[i+1] >> 1) ^ -(nums[i+1] & 1)
        lat += dlat
        lng += dlng
        la = lat/factor
        lo = lng/factor
        if 29 <= la <= 34 and 34 <= lo <= 37:
            points.append((la,lo))
    return points


def google_polyline(points):
    last_lat = last_lng = 0
    out = []
    def enc(n):
        n = n << 1 if n >= 0 else ~(n << 1)
        while n >= 0x20:
            out.append(chr((0x20 | (n & 0x1f)) + 63))
            n >>= 5
        out.append(chr(n + 63))
    for lat, lng in points:
        a, b = round(lat*1e5), round(lng*1e5)
        enc(a-last_lat);enc(b-last_lng)
        last_lat,last_lng = a,b
    return "".join(out)


def path_result(path, q):
    path = unquote(path)
    root = "/api/where/"
    if path == "/healthz":
        return 200, {"ok": True, "service": "israel-oba-compat", "database": CATALOG.exists()}
    if path == "/otp/routers/default/plan":
        try:
            origin,destination,body=otp_adapter.request_payload(q)
            raw=fetch_mot("planner","RoutePlanning/GetRoutes",body=body,ttl=45)
            if not isinstance(raw,list):
                return 503, {"error": "Trip planner response was not a valid itinerary list"}
            return 200,otp_adapter.map_response(raw,origin,destination,decode_here_polyline,google_polyline)
        except MOTUnavailable as exc:
            return 503,{"error":str(exc)}
        except (ValueError,TypeError) as exc:
            return 400,{"error":str(exc)[:180]}
    if not path.startswith(root):
        return 404, envelope(None, 404, "Unknown path")
    endpoint = path[len(root):]
    if endpoint == "agencies-with-coverage.json":
        # Coverage is a regional view, not an invented provider geometry.
        return 200, envelope({"list": [{"agencyId": "mot:agency:1", "lat": 31.6, "lon": 35.0,
                                          "latSpan": 3.5, "lonSpan": 2.0}],
                              "references": refs(agencies=[agency()])})
    if endpoint.startswith("routes-for-agency/"):
        # Bootstrap from an authentic busy Jerusalem stop, never hardcode fictional routes.
        with _lock:
            empty = not _known_routes
        if empty:
            try:
                live = stop_details(5997)
                with _lock:
                    _known_routes.update({r["id"]: r for r in (
                        route_summary(a) for a in live.get("routesInStop", []))})
            except MOTUnavailable:
                pass
        with _lock:
            index = list(_known_routes.values())
        return 200, envelope({"list": index, "limitExceeded": False,
                              "references": refs(routes=index, agencies=[agency()])})
    if endpoint == "stops-for-location.json":
        stops = query_stops(q.get("lat",["31.78"])[0], q.get("lon",["35.21"])[0],
                            q.get("latSpan",["0.06"])[0], q.get("lonSpan",["0.06"])[0],
                            q.get("query",[""])[0], q.get("maxCount",["120"])[0])
        serial = [serialize_stop(s) for s in stops]
        return 200, envelope({"list":serial,"limitExceeded":len(serial)>=120,"outOfRange":False,
                              "references":refs(stops=serial)})
    if endpoint == "routes-for-location.json":
        term = q.get("query",[""])[0].strip()
        if term:
            try:
                live = fetch_mot("planner", "AutoComplete/SearchLines",
                                 {"searchTerm": term}, ttl=180)
                newly_found = [route_summary(r) for r in (live or []) if r.get("routeId")]
                with _lock:
                    _known_routes.update({r["id"]:r for r in newly_found})
            except MOTUnavailable:
                pass
        with _lock:
            routes = [r for r in _known_routes.values()
                      if not term or term in r["shortName"] or term in r["longName"]][:100]
        return 200, envelope({"list":routes,"outOfRange":False,
                              "limitExceeded":len(routes)>=100,
                              "references":refs(routes=routes,agencies=[agency()])})
    m = re.fullmatch(r"stop/([^/]+)\.json", endpoint)
    if m:
        code = stop_code(m[1])
        stop, routes, agencies = stop_and_routes(code, m[1]) if code else (None, [], [])
        if not stop: return 200, envelope({"entry":None,"references":refs()})
        with _lock:
            _known_routes.update({r["id"]:r for r in routes})
        return 200, envelope({"entry":stop,"references":refs(stops=[stop],routes=routes,agencies=agencies)})
    m = re.fullmatch(r"arrivals-and-departures-for-stop/([^/]+)\.json", endpoint)
    if m:
        code = stop_code(m[1])
        stop, routes, agencies = stop_and_routes(code, m[1]) if code else (None, [], [])
        if not stop: return 200, envelope({"entry":None,"references":refs()})
        with _lock: _known_routes.update({r["id"]:r for r in routes})
        raw = {}
        try: raw = stop_details(code) or {}
        except MOTUnavailable: pass
        if raw.get("routesInStop"):
            raw = {**raw, "stopTimes":list(raw.get("stopTimes") or [])+
                   fetch_next_stop_times(raw,code)}
        arrivals, trips = get_arrivals(raw, code, m[1], int(q.get("minutesBefore",[0])[0]),
                                       min(720,int(q.get("minutesAfter",[60])[0])))
        return 200, envelope({"entry":{"stopId":m[1],"arrivalsAndDepartures":arrivals,
                                        "nearbyStopIds":[],"situationIds":[]},
                              "references":refs(stops=[stop],routes=routes,agencies=agencies,trips=trips)})
    m = re.fullmatch(r"route/([^/]+)\.json", endpoint)
    if m:
        rid = route_id(m[1])
        try: data = route_details(rid)
        except MOTUnavailable: return 503, envelope(None,503,"Route data provider unavailable")
        r=route_summary(data); with_routes=[r]
        with _lock: _known_routes[r["id"]]=r
        return 200, envelope({"entry":r,"references":refs(routes=with_routes,agencies=[agency(data.get("agencyId"),data.get("agencyName"))])})
    m = re.fullmatch(r"stops-for-route/([^/]+)\.json", endpoint)
    if m:
        rid=route_id(m[1])
        try: data=route_details(rid)
        except MOTUnavailable: return 503,envelope(None,503,"Route data provider unavailable")
        r=route_summary(data)
        stops=[serialize_stop(s) for s in data.get("stops",[]) if s.get("stopcode")]
        ids=[s["id"] for s in stops]
        geom=google_polyline(decode_here_polyline(data.get("polyline")))
        group={"id":"0","name":{"name":name(data.get("headsign")),"type":"destination"},
               "stopIds":ids,"polylines":[{"points":geom}] if geom else []}
        entry={"routeId":r["id"],"stopIds":ids,"polylines":[{"points":geom}] if geom else [],
               "stopGroupings":[{"ordered":True,"type":"direction","stopGroups":[group]}]}
        return 200,envelope({"entry":entry,"references":refs(stops=stops,routes=[r],
                              agencies=[agency(data.get("agencyId"),data.get("agencyName"))])})
    m=re.fullmatch(r"shape/([^/]+)\.json",endpoint)
    if m:
        rid=route_id(m[1])
        try: data=route_details(rid)
        except MOTUnavailable: return 503,envelope(None,503,"Route geometry provider unavailable")
        geom=google_polyline(decode_here_polyline(data.get("polyline")))
        return 200,envelope({"entry":{"points":geom} if geom else None,"references":refs()})
    m=re.fullmatch(r"schedule-for-stop/([^/]+)\.json",endpoint)
    if m:
        # No fake timetables: return explicit empty set when not actually available.
        return 200,envelope({"entry":{"stopId":m[1],"stopRouteSchedules":[],
                                      "date":ms()},"references":refs()})
    m=re.fullmatch(r"(trip-details|trip|trips-for-route|arrival-and-departure-for-stop)/([^/]+)\.json",endpoint)
    if m:
        return 200,envelope({"entry":None,"list":[],"references":refs()})
    return 404,envelope(None,404,"Endpoint not implemented: "+endpoint[:80])


_known_routes = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        if os.environ.get("ISRAEL_OBA_LOG","0") == "1":
            super().log_message(format,*args)

    def do_GET(self):
        parsed = urlsplit(self.path)
        params = parse_qs(parsed.query)
        try:
            status, result = path_result(parsed.path, params)
        except (ValueError, TypeError, sqlite3.Error, FileNotFoundError) as exc:
            status, result = 400, {"error": str(exc)[:180]}
        except MOTUnavailable as exc:
            status, result = 503, {"error": str(exc)[:180]}
        data = json.dumps(result,ensure_ascii=False,separators=(",",":")).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__=="__main__":
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    print(f"Israel OBA bridge ready on http://{HOST}:{PORT}; catalog={CATALOG.exists()}",flush=True)
    server.serve_forever()
