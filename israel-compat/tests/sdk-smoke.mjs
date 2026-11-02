import onebusaway from 'onebusaway-sdk';
const api = new onebusaway({ baseURL: 'http://127.0.0.1:8770', apiKey: 'test', defaultQuery: { version: 2 } });
const stops = await api.stopsForLocation.list({ lat:31.815188, lon:35.203022, latSpan:0.01, lonSpan:0.01 });
console.log('SDK_STOPS',stops.code,stops.data?.list?.length);
const details = await api.stop.retrieve('mot:stop:5997');
console.log('SDK_STOP',details.code,details.data?.entry?.name,details.data?.entry?.routeIds?.length);
const arrivals = await api.arrivalAndDeparture.list('mot:stop:5997', { minutesAfter:60 });
console.log('SDK_ARRIVALS',arrivals.code,arrivals.data?.entry?.arrivalsAndDepartures?.length);
