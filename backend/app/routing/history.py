"""Opt-in, device-scoped snapshots; GPS ends are only stored behind a local test switch."""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from pydantic import BaseModel

from app.api.schemas import RouteRequest, RoutesResponse


class SavedRoute(BaseModel):
    id: str
    saved_at: datetime
    request: RouteRequest
    result: RoutesResponse
    is_historical: bool = True


class RouteHistory(BaseModel):
    items: list[SavedRoute]


@contextmanager
def database():
    path = Path(os.environ.get('ROUTE_HISTORY_DB',
        str(Path(__file__).resolve().parents[2] / 'data' / 'route_history.sqlite3')))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    try:
        connection.execute('''CREATE TABLE IF NOT EXISTS route_history (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT NOT NULL, id TEXT NOT NULL UNIQUE,
            origin TEXT NOT NULL, destination TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            UNIQUE(owner, origin, destination))''')
        with connection:
            yield connection
    finally:
        connection.close()


def owner_hash(key: str) -> str:
    return sha256(key.encode('utf-8')).hexdigest()


# test only, off unless you set it. normally a walk from (or to) your location
# is never saved, because ADR-010 and the privacy rules say not to keep where
# someone was. turning this on saves every calculated route so the list can be
# tried out, and a GPS end is filed under "current" so walks from wherever you
# happen to be to the same place replace each other instead of piling up.
def saves_gps_routes() -> bool:
    return os.environ.get('ROUTE_HISTORY_INCLUDE_GPS') == '1'


def endpoint_key(endpoint) -> str | None:
    if endpoint.place_id is not None:
        return endpoint.place_id
    return 'current' if saves_gps_routes() else None


def save(key: str, request: RouteRequest, result: RoutesResponse) -> bool:
    origin, destination = endpoint_key(request.origin), endpoint_key(request.destination)
    if origin is None or destination is None:
        return False
    snapshot = SavedRoute(id=str(uuid4()), saved_at=datetime.now(timezone.utc),
                          request=request, result=result)
    owner = owner_hash(key)
    with database() as connection:
        # Serialize read/replace/prune across concurrent requests and processes.
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('DELETE FROM route_history WHERE owner=? AND origin=? AND destination=?',
                           (owner, origin, destination))
        connection.execute('INSERT INTO route_history(owner,id,origin,destination,snapshot) VALUES(?,?,?,?,?)',
                           (owner, snapshot.id, origin, destination, snapshot.model_dump_json()))
        connection.execute('''DELETE FROM route_history WHERE owner=? AND sequence NOT IN
            (SELECT sequence FROM route_history WHERE owner=? ORDER BY sequence DESC LIMIT 5)''',
                           (owner, owner))
    return True


def read(key: str, entry_id: str | None = None) -> list[SavedRoute]:
    with database() as connection:
        if entry_id is None:
            rows = connection.execute(
                'SELECT snapshot FROM route_history WHERE owner=? ORDER BY sequence DESC LIMIT 5',
                (owner_hash(key),)).fetchall()
        else:
            rows = connection.execute('SELECT snapshot FROM route_history WHERE owner=? AND id=?',
                                      (owner_hash(key), entry_id)).fetchall()
    return [SavedRoute.model_validate_json(row[0]) for row in rows]
