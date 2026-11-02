"""Real MOT planner response -> OpenTripPlanner 1.x shape for Wayfinder.

No invented itineraries, predictions, stop times or geometry.
"""
from __future__ import annotations
import math
from datetime import datetime, timezone
from urllib.parse import parse_qs


def ms(value):
    if not value:
        return None
    try:
        d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if d.tzinfo is None:
            # Ministry of Transport's local-time timestamps follow Asia/Jerusalem.
            from zoneinfo import ZoneInfo
            d=d.replace(tzinfo=ZoneInfo("Asia/Jerusalem"))
        return int(d.timestamp()*1000)
    except (ValueError, TypeError, OverflowError):
        return None


def place(raw, fallback):
    raw=raw or {}
    loc=raw.get("location") or {}
    code=raw.get("code")
    return {
        "name":str(raw.get("name") or fallback.get("name") or ""),
        "lat":float(loc.get("lat") or fallback.get("lat") or 0),
        "lon":float(loc.get("lng") or fallback.get("lon") or 0),
        "vertexType":"STOP" if code else "NORMAL",
        **({"stopId":"mot:stop:"+str(code),"stopCode":str(code)} if code else {})
    }


def map_response(raw, origin, destination, decode_polyline, encode_polyline):
    """Port of IsraelMOT/OTPAdapter/MOTItineraryMapper.swift's verified contract."""
    mapped=[]
    for route in raw if isinstance(raw,list) else []:
        sections=route.get("sections") or []
        legs=[]
        walk_time=transit_time=0
        walk_distance=0.0
        valid=True
        for section in sections:
            departure=section.get("departure") or {}
            arrival=section.get("arrival") or {}
            start=ms(departure.get("time"))
            end=ms(arrival.get("time"))
            if start is None or end is None or end < start:
                valid=False
                break
            kind=str(section.get("type") or "").lower()
            transport=section.get("transport") or {}
            is_walk=kind in ("walk","walking","pedestrian")
            mode=("WALK" if is_walk else
                  "TRAM" if kind in ("light_rail","lightrail","lightRail".lower()) else
                  "RAIL" if kind in ("train","regionaltrain") else
                  "BUS")
            travel=section.get("travelSummary") or {}
            duration=int(travel.get("duration") or (end-start)//1000)
            distance=float(travel.get("length") or 0)
            if is_walk:
                walk_time+=duration
                walk_distance+=distance
            else: transit_time+=duration
            geom=encode_polyline(decode_polyline(section.get("polyline")))
            source=place(departure.get("place"),origin)
            target=place(arrival.get("place"),destination)
            def stop_step(step):
                return {"streetName":str(step.get("instruction") or ""),
                        "distance":float(step.get("length") or 0),
                        "relativeDirection": ("LEFT" if str(step.get("direction")).lower()=="left"
                                              else "RIGHT" if str(step.get("direction")).lower()=="right"
                                              else "DEPART"),
                        "lat":source["lat"],"lon":source["lon"]}
            legs.append({
                "startTime":start,"endTime":end,"mode":mode,"transitLeg":not is_walk,
                "duration":duration,"distance":distance,
                "route":transport.get("shortName") or transport.get("name"),
                "headsign":transport.get("headsign"),
                "routeType":0 if mode=="TRAM" else 2 if mode=="RAIL" else 3,
                "routeColor":str(transport.get("color") or "#1565C0").lstrip("#"),
                "routeTextColor":"FFFFFF",
                "from":source,"to":target,"agencyName":(section.get("agency") or {}).get("name"),
                "legGeometry":{"points":geom,"length":len(decode_polyline(section.get("polyline")))},
                "steps":[stop_step(step) for step in section.get("actions") or []],
                "intermediateStops":[place(v.get("departure",{}).get("place"),source)
                                     for v in section.get("intermediateStops") or []],
                "realTime":bool((departure.get("nextStopsTimes") or [{}])[0].get("isRealTime",False)),
                "departureDelay":0,"arrivalDelay":0
            })
        if not valid or not legs:
            continue
        duration=max((legs[-1]["endTime"]-legs[0]["startTime"])//1000,walk_time+transit_time)
        transit_count=sum(1 for l in legs if l["transitLeg"])
        mapped.append({
            "duration":duration,"startTime":legs[0]["startTime"],"endTime":legs[-1]["endTime"],
            "walkTime":walk_time,"transitTime":transit_time,
            "waitingTime":max(duration-walk_time-transit_time,0),
            "walkDistance":walk_distance,"transfers":max(transit_count-1,0),
            "walkLimitExceeded":False,"elevationLost":0,"elevationGained":0,"legs":legs
        })
    return {"requestParameters":{},"plan":{"date":mapped[0]["startTime"] if mapped else 0,
            "from":place({},origin),"to":place({},destination),"itineraries":mapped}}


def parse_coord(value):
    raw=str(value or "")
    parts=raw.split(",")
    if len(parts)!=2:raise ValueError("fromPlace/toPlace must be lat,lon")
    lat,lon=map(float,parts)
    if not (-90<=lat<=90 and -180<=lon<=180):raise ValueError("Coordinates out of range")
    return {"lat":lat,"lon":lon}


def request_payload(q):
    """Build correct MOT GetRoutes request from the Wayfinder OTP query."""
    origin=parse_coord(q.get("fromPlace",[""])[0])
    destination=parse_coord(q.get("toPlace",[""])[0])
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try: tz=ZoneInfo("Asia/Jerusalem")
    except Exception: tz=datetime.now().astimezone().tzinfo
    raw_date=q.get("date",[""])[0]
    raw_time=q.get("time",[""])[0]
    try:
        if raw_date and raw_time:
            t=datetime.strptime(raw_date+" "+raw_time,"%m-%d-%Y %I:%M %p")
            t=t.replace(tzinfo=tz)
        else:t=datetime.now(tz)
    except Exception:
        t=datetime.now(tz)
    options={
        "sortBy":0,"isAccessible":q.get("wheelchair",["false"])[0]=="true",
        "maxTravelTime":600,"changes":True,"maxWalkTime":120,
        "transportationsForInitialUse":["bus","carmelit","lightRail","publicTaxi","rahbalit","train"],
        "transportations":["bus","privateBus","lightRail","regionalTrain"]
    }
    field="arrivalTime" if q.get("arriveBy",["false"])[0]=="true" else "departureTime"
    options[field]=t.isoformat(timespec="seconds")
    address=lambda p:{"coordinates":{"lat":p["lat"],"lng":p["lon"]},"addressDetails":{"label":"מוצא"}}
    body={"route":{"origin":address(origin),"destination":address(destination),"options":options},
          "returnedRouteOptions":{"language":"he","isFutureSearch":True}}
    return origin,destination,body
