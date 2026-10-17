from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, model_validator

Coordinate = tuple[float, float]

class Endpoint(BaseModel):
    place_id: str | None = None
    coordinate: Coordinate | None = None

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.place_id is None) == (self.coordinate is None):
            raise ValueError("Specify exactly one of place_id or coordinate")
        if self.coordinate is not None:
            lon, lat = self.coordinate
            if not (-118.49 <= lon <= -118.40 and 34.04 <= lat <= 34.10):
                raise ValueError("Coordinates must be within the UCLA service boundary")
        return self

class RouteRequest(BaseModel):
    origin: Endpoint
    destination: Endpoint
    departure_time: datetime
    temperature_c: float = Field(default=23.0, ge=-20, le=55)

    @model_validator(mode="after")
    def require_tz(self):
        if self.departure_time.utcoffset() is None:
            raise ValueError("departure_time must have a timezone offset")
        return self

class LineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[Coordinate]

class RouteSegment(BaseModel):
    shade_state: Literal["shade", "sun", "unknown"]
    duration_s: float
    sun_seconds: float | None  # NULL if no shade data exists
    unknown_seconds: float
    geometry: LineString

class RouteStep(BaseModel):
    maneuver: Literal["depart", "straight", "slight_left", "slight_right", "left", "right",
                      "sharp_left", "sharp_right", "arrive"]
    instruction: str
    way_name: str | None  # OSM name when the path has one; unnamed walkways are None
    distance_m: float  # walked from this step until the next maneuver

class RouteResponseItem(BaseModel):
    id: str
    mode: Literal["fastest", "recommended", "maximum_shade"]
    same_as: str | None
    duration_s: float
    distance_m: float
    sun_seconds: float | None
    unknown_seconds: float
    optimization_quality: Literal["shortest_time", "candidate_search", "unavailable"]
    geometry: LineString
    segments: list[RouteSegment]
    steps: list[RouteStep]

class Conditions(BaseModel):
    temperature_c: float
    temperature_source: Literal["user"] = "user"
    shade_model: Literal["unavailable", "geometry_estimate"] = "unavailable"
    data_as_of: str | None = None
    model_limitations: list[str]

class RoutesResponse(BaseModel):
    conditions: Conditions
    routes: list[RouteResponseItem]
