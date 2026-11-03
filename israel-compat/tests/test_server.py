"""Regression suite for the Israel REST bridge against real iOS catalogue/fixtures."""
import importlib.util
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(HERE))
SPEC=importlib.util.spec_from_file_location("israel_mot_bridge",HERE/"server.py")
bridge=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)
IOS_FIXTURES=HERE.parents[1]/"onebusaway-ios"/"IsraelMOT"/"Tests"/"Fixtures"


class APIContractTests(unittest.TestCase):
    def test_local_catalog_and_rtree(self):
        self.assertTrue(bridge.CATALOG.exists())
        near=bridge.query_stops(lat=31.815188, lon=35.203022, lat_span=0.01,lon_span=0.01)
        self.assertGreater(len(near),2)
        self.assertTrue(any(str(x['stop_code'])=='5997' for x in near))
        for s in near:
            self.assertGreater(float(s['lat']),29)
            self.assertLess(float(s['lat']),34)

    def test_envelope_and_references(self):
        s,data=bridge.path_result('/api/where/stops-for-location.json',
                                  {'lat':['31.815188'],'lon':['35.203022'],
                                   'latSpan':['0.01'],'lonSpan':['0.01']})
        self.assertEqual(s,200)
        self.assertEqual(data['code'],200)
        self.assertTrue(data['data']['list'])
        self.assertIn('references', data['data'])
        self.assertIn('stops',data['data']['references'])

    def test_search_is_local(self):
        s,data=bridge.path_result('/api/where/stops-for-location.json',{'query':['סילבר']})
        self.assertEqual(s,200)
        self.assertGreater(len(data['data']['list']),0)

    def test_otp_version_negotiation(self):
        code, payload = bridge.path_result("/otp", {})
        self.assertEqual(code, 200)
        self.assertEqual(payload["version"]["major"], 1)

    def test_ios_exact_route_payload(self):
        from otp_adapter import request_payload
        src,dest,payload=request_payload({
            "fromPlace":["31.816342207,35.203175915"],
            "toPlace":["31.78948,35.22441"],
            "date":["11-03-2026"],"time":["5:30 PM"]})
        route=payload["route"]
        self.assertIn("stop",route)
        self.assertIsNone(route["stop"])
        self.assertIsNone(route["options"]["arrivalTime"])
        self.assertEqual(route["options"]["departureTime"],"2026-11-03T17:30:00")
        self.assertEqual(route["origin"]["addressDetails"]["label"],"Origin")
        self.assertNotIn("+02:00",route["options"]["departureTime"])
        self.assertEqual(payload["returnedRouteOptions"]["language"],"he")

    def test_mot_address_autocomplete(self):
        from unittest.mock import patch
        places=[{"title":"בית ישראל, ירושלים","id":"a","coordinates":{
                    "lat":31.78948,"lng":35.22441}},
                {"title":"מחוץ לישראל","coordinates":{"lat":40,"lng":-1}}]
        with patch.object(bridge,"fetch_mot",return_value=places) as remote:
            status,body=bridge.path_result("/geo/search",{"query":["בית ישראל"]})
        self.assertEqual(status,200)
        self.assertEqual(len(body["suggestions"]),1)
        self.assertEqual(body["suggestions"][0]["name"],"בית ישראל, ירושלים")
        self.assertAlmostEqual(body["location"]["geometry"]["location"]["lat"],31.78948)
        remote.assert_called_once()

    def test_trip_details_use_real_stop_pattern_no_invented_times(self):
        from unittest.mock import patch
        route={"routeId":33285,"routeName":"31","routeLongName":"גילה",
               "agencyId":1,"stops":[
                    {"stopcode":5997,"stopid":11622,"name":{"he":"ליפסקי"},"lat":31.8,"lng":35.2},
                    {"stopcode":5998,"stopid":11623,"name":{"he":"השקד"},"lat":31.79,"lng":35.21}]}
        with patch.object(bridge,"route_details",return_value=route):
            status,body=bridge.path_result(
                "/api/where/trip-details/mot:trip:33285:123456789.json",{})
        self.assertEqual(status,200)
        entry=body["data"]["entry"]
        self.assertTrue(entry["routeOnly"])
        self.assertEqual(len(entry["schedule"]["stopTimes"]),2)
        self.assertIsNone(entry["schedule"]["stopTimes"][0]["arrivalTime"])
        self.assertEqual(body["data"]["references"]["stops"][0]["name"],"ליפסקי")

    def test_agency_bootstrap(self):
        s,data=bridge.path_result('/api/where/agencies-with-coverage.json',{})
        self.assertEqual(s,200)
        self.assertEqual(data['data']['list'][0]['agencyId'],'mot:agency:1')

    def test_stop_and_route_ids(self):
        self.assertEqual(bridge.stop_code('mot:stop:5997:11622'),5997)
        self.assertEqual(bridge.route_id('mot:shape:33285'),33285)
        self.assertEqual(bridge.route_id('mot:route:33285'),33285)

    def test_real_stop_time_endpoint_mapping(self):
        from unittest.mock import patch
        sample={"5997":{"stopTimes":[{
            "arrivalTime":"2026-11-03T05:38:59","isRealTime":False,
            "minutesToArrival":273.5}]}}
        route={"routeId":33285,"routeDesc":"15031-1-0","routeName":"31",
               "routeLongName":"רמות-ירושלים<->גילה"}
        with patch.object(bridge,"fetch_mot",return_value=sample) as remote:
            mapped=bridge.fetch_next_stop_times({"routesInStop":[route]},5997)
        self.assertEqual(len(mapped),1)
        self.assertEqual(mapped[0]["routeId"],33285)
        self.assertEqual(mapped[0]["routeName"],"31")
        self.assertFalse(mapped[0]["isRealTime"])
        self.assertEqual(remote.call_args.kwargs.get("body"),
                         {"routeDesc":"15031-1-0","stopCodes":[5997]})

    def test_no_fabricated_arrivals(self):
        sample={'routesInStop':[{'routeId':33285,'routeName':'31',
                                 'stops':[{'stopcode':5997,'nextStopsTimes':None}]}],
                'stopTimes':[]}
        a,t=bridge.get_arrivals(sample,5997,'mot:stop:5997')
        self.assertEqual(a,[])
        self.assertEqual(t,[])

    def test_route_map_geometry_real_fixture(self):
        fixture=IOS_FIXTURES/'route_33285_fulldata.json'
        if not fixture.exists(): self.skipTest('Optional iOS fixture unavailable')
        source=json.loads(fixture.read_text(encoding='utf-8'))['data']
        shape=bridge.decode_here_polyline(source['polyline'])
        self.assertGreater(len(shape),500)
        self.assertTrue(all(29<=lat<=34 and 34<=lon<=37 for lat,lon in shape))
        encoded=bridge.google_polyline(shape)
        self.assertGreater(len(encoded),500)

    def test_transit_line_numbers_are_preserved_for_wayfinder_badges(self):
        from otp_adapter import map_response
        departure={"time":"2026-11-03T16:00:00","place":{"name":"A",
                    "location":{"lat":31.8,"lng":35.2}}}
        arrival={"time":"2026-11-03T16:10:00","place":{"name":"B",
                  "location":{"lat":31.79,"lng":35.21}}}
        sections=[{"type":"transit","departure":departure,"arrival":arrival,
                   "travelSummary":{"length":1200,"duration":600},
                   "transport":{"mode":"bus","shortName":"64","name":"64",
                                "routeId":10459,"headsign":"גבעת שאול"},
                   "polyline":""}]
        itineraries=map_response([{"sections":sections}],
                                  {"lat":31.8,"lon":35.2},{"lat":31.79,"lon":35.21},
                                  lambda x: [],lambda x:"")["plan"]["itineraries"]
        self.assertEqual(len(itineraries),1)
        leg=itineraries[0]["legs"][0]
        self.assertEqual(leg["mode"],"BUS")
        self.assertEqual(leg["routeShortName"],"64")
        self.assertEqual(leg["route"],"64")
        self.assertEqual(leg["routeId"],"mot:route:10459")
        self.assertEqual(leg["headsign"],"גבעת שאול")

    def test_planner_unavailable_not_fabricated(self):
        from unittest.mock import patch
        with patch.object(bridge, "fetch_mot", side_effect=bridge.MOTUnavailable("MOT HTTP 503")):
            s,p=bridge.path_result('/otp/routers/default/plan',{
                "fromPlace":["31.815188,35.203022"],"toPlace":["31.78913,35.20317"]})
        self.assertEqual(s,503)
        self.assertIn('error',p)

    def test_verified_planner_fixture_maps_to_real_otp_itinerary(self):
        fixture=IOS_FIXTURES/'route_planning_success_fixture.json'
        if not fixture.exists():self.skipTest('Optional iOS fixture unavailable')
        raw=json.loads(fixture.read_text(encoding='utf-8'))['data']
        from otp_adapter import map_response
        doc=map_response(raw, {"lat":31.78913,"lon":35.20317},
                        {"lat":31.81518,"lon":35.20302},
                        bridge.decode_here_polyline,bridge.google_polyline)
        self.assertTrue(doc['plan']['itineraries'])
        first=doc['plan']['itineraries'][0]
        self.assertGreater(first['duration'],0)
        self.assertTrue(first['legs'])
        self.assertEqual(first['legs'][0]['mode'],'WALK')
        self.assertEqual(first['legs'][1]['mode'],'BUS')


if __name__=='__main__':
    unittest.main()
