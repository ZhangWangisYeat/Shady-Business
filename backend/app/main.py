from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.schemas import RouteRequest, RoutesResponse
from app.places.catalog import PLACES, search_places, find_place
from app.routing.graph import GraphDataUnavailable, load_graph
from app.routing.service import build_routes, EndpointTooFar, GraphUnavailable, NoRoute, SameEndpoint
from app.shade.model import ShadeDataUnavailable, load_model, model_coverage_status

app=FastAPI(title="Shady Business API",version="0.1.0")
# Local development via native devices does not use browser CORS; set explicit origins for any web client later.


def problem(code: str, message: str, *, retryable: bool=False, field: str | None=None):
    detail={'code':code,'message':message,'retryable':retryable}
    if field is not None:
        detail['field']=field
    return detail


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    first=exc.errors()[0]
    field='.'.join(str(part) for part in first.get('loc',())[1:]) or None
    message=str(first.get('msg',''))
    if 'UCLA service boundary' in message:
        code='OUTSIDE_SERVICE_AREA'
        friendly='Choose a location inside the UCLA service area.'
    elif field == 'temperature_c':
        code='INVALID_TEMPERATURE'
        friendly='Temperature must be between -20°C and 55°C.'
    elif field == 'departure_time' or 'timezone offset' in message:
        code='INVALID_DEPARTURE_TIME'
        friendly='Departure time must include a timezone offset.'
    else:
        code='INVALID_REQUEST'
        friendly='Check the route request and try again.'
    return JSONResponse(status_code=422,content={'detail':problem(code,friendly,field=field)})

@app.get('/api/health')
def health():
    try:
        model=load_model()
    except ShadeDataUnavailable:
        model=None
    try:
        graph=load_graph()
    except GraphDataUnavailable:
        graph=None
    return {'status':'ok','dataset_status':'ready' if graph else 'not_loaded',
            'shade_status':'modeled' if model else 'unavailable',
            'shade_coverage':model_coverage_status(model)}

@app.get('/api/places')
def places(q: str=Query(default='',max_length=100)):
    return {'places':[{'id':p.id,'name':p.name,'coordinate':p.coordinate} for p in search_places(q)]}

@app.post('/api/routes',response_model=RoutesResponse)
def routes(body: RouteRequest):
    def resolve(endpoint, field):
        if endpoint.coordinate is not None: return endpoint.coordinate
        place=find_place(endpoint.place_id)
        if place is None:
            raise HTTPException(status_code=404,detail=problem(
                'PLACE_NOT_FOUND','That UCLA location is no longer available. Please choose it again.',field=field))
        return place.coordinate
    try:
        return build_routes(resolve(body.origin,'origin'),resolve(body.destination,'destination'),body.departure_time,body.temperature_c)
    except GraphUnavailable as exc:
        raise HTTPException(status_code=503,headers={'Retry-After':'3'},detail=problem(
            'GRAPH_NOT_READY','Walking routes are temporarily unavailable. Please try again.',retryable=True)) from exc
    except EndpointTooFar as exc:
        raise HTTPException(status_code=422,detail=problem(
            'SNAP_TOO_FAR',f'The {exc.field} is too far from a campus walking path.',field=exc.field)) from exc
    except SameEndpoint as exc:
        raise HTTPException(status_code=422,detail=problem(
            'SAME_ENDPOINT','Start and destination are too close. Choose another destination.',field='destination')) from exc
    except NoRoute as exc:
        raise HTTPException(status_code=422,detail=problem(
            'NO_WALKABLE_PATH','No connected walking route was found. Choose another campus location.')) from exc
