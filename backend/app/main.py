from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from app.api.schemas import RouteRequest
from app.places.catalog import search_places, find_place, catalog_attribution
from app.routing.graph import load_graph
from app.routing.service import build_routes, GraphUnavailable, NoRoute
from app.shade.model import load_model

app=FastAPI(title="Shady Business API",version="0.1.0")
# Local development via native devices does not use browser CORS; set explicit origins for any web client later.

@app.get('/api/health')
def health():
    return {'status':'ok','dataset_status':'ready' if load_graph() else 'not_loaded','shade_status':'modeled' if load_model() else 'unavailable'}

@app.get('/api/places')
def places(q: str=Query(default='',max_length=100), limit: int=Query(default=8,ge=1,le=20)):
    return {'places':[{'id':p.id,'name':p.name,'coordinate':p.coordinate,'category':p.category,'address':p.address}
                      for p in search_places(q,limit)],
            'attribution':catalog_attribution()}

@app.post('/api/routes')
def routes(body: RouteRequest):
    def resolve(endpoint):
        if endpoint.coordinate is not None: return endpoint.coordinate
        place=find_place(endpoint.place_id)
        if place is None: raise HTTPException(status_code=404,detail={'code':'PLACE_NOT_FOUND','message':'Unknown UCLA location'})
        return place.coordinate
    try:
        return build_routes(resolve(body.origin),resolve(body.destination),body.departure_time,body.temperature_c)
    except (GraphUnavailable,NoRoute,ValueError) as exc:
        status=503 if isinstance(exc,GraphUnavailable) else 422
        raise HTTPException(status_code=status,detail={'code':'GRAPH_NOT_READY' if status==503 else 'NO_WALKABLE_PATH','message':str(exc)}) from exc
