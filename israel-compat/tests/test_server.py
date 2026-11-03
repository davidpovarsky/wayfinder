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
