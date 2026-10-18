#!/usr/bin/env python3
"""Step 2 (network): fetch a few photos of each gap site, aerial first, then Mapillary street level.

Needs MAPILLARY_TOKEN (a free client token from mapillary.com/dashboard/developers)
for street-level photos. Aerial tiles are USDA NAIP (0.6 m, public domain) from
Microsoft Planetary Computer, which needs no key. Photos and their provenance land in
backend/data/vision/, which is gitignored: Mapillary photos are CC BY-SA, so
they can be analyzed and credited but shouldn't be committed.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.vision.geo import bbox_around, meters_between  # noqa: E402
from app.vision.keys import load_keys  # noqa: E402

VISION = ROOT / "backend/data/vision"
USER_AGENT = "shady-business/0.1 (UCLA campus walking app prototype)"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
CROP = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"
MAPILLARY = "https://graph.mapillary.com/images"
FIELDS = "id,captured_at,compass_angle,computed_compass_angle,computed_geometry,geometry,is_pano,camera_parameters,thumb_1024_url,creator"


def get(url: str, headers: dict | None = None, timeout: float = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def aerial(site: dict, size_m: float, pixels: int) -> dict | None:
    bbox = bbox_around(*site["coordinate"], size_m)
    # usgs's own naip servers timed out (504) and then reset every connection,
    # so the same public-domain naip photos come from microsoft's planetary
    # computer mirror instead: free, no key, and a crop comes back in about a second.
    search = json.dumps({"collections": ["naip"], "bbox": list(bbox), "limit": 1,
                         "sortby": [{"field": "datetime", "direction": "desc"}]}).encode()
    try:
        request = urllib.request.Request(STAC, search, {"User-Agent": USER_AGENT, "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            items = json.load(response)["features"]
        if not items:
            return None
        item = items[0]
        corners = ",".join(f"{v:.6f}" for v in bbox)
        data = get(f"{CROP}/{corners}/{pixels}x{pixels}.png?collection=naip&item={item['id']}&assets=image"
                   f"&asset_bidx=image%7C1,2,3", timeout=90)
    except (urllib.error.URLError, TimeoutError, KeyError) as exc:
        print(f"    aerial failed: {exc}", file=sys.stderr)
        return None
    # a png starts with a byte then the letters PNG; anything else is an error page
    if data[1:4] != b"PNG":
        return None
    photo_id = f"naip-{site['id']}"
    path = VISION / "photos" / f"{photo_id}.png"
    path.write_bytes(data)
    return {"id": photo_id, "kind": "aerial", "file": str(path.relative_to(VISION)), "mime": "image/png",
            # the crop comes back in plain longitude/latitude, so grid positions
            # map linearly in degrees (geo.grid_to_lonlat reads this)
            "bbox": list(bbox), "grid_crs": "EPSG:4326", "size_m": size_m,
            "captured_at": f"{item['properties']['datetime'][:10]} (USDA NAIP survey; time of day not given)",
            "source": f"USDA NAIP {item['id']} via Microsoft Planetary Computer", "license": "Public domain (USDA NAIP)",
            "attribution": "USDA National Agriculture Imagery Program (NAIP), via Microsoft Planetary Computer"}


def street(site: dict, token: str, per_site: int, radius_m: float) -> list[dict]:
    bbox = bbox_around(*site["coordinate"], radius_m * 2)
    query = urllib.parse.urlencode({"fields": FIELDS, "bbox": ",".join(f"{v:.6f}" for v in bbox), "limit": 60})
    # the token goes in a header so it never shows up in a url or a log
    found = json.loads(get(f"{MAPILLARY}?{query}", {"Authorization": f"OAuth {token}"}))["data"]
    def where(image):
        geometry = image.get("computed_geometry") or image.get("geometry")
        return tuple(geometry["coordinates"]) if geometry else None
    usable = [i for i in found if where(i) and i.get("thumb_1024_url")
              and meters_between(where(i), site["coordinate"]) <= radius_m]
    # newest first, then spread out the directions: three photos facing the
    # same way see the same trees, three facing different ways see the site
    usable.sort(key=lambda i: -(i.get("captured_at") or 0))
    picked = []
    for image in usable:
        heading = image.get("computed_compass_angle", image.get("compass_angle")) or 0
        if all(abs((heading - p["heading"] + 180) % 360 - 180) >= 60 for p in picked):
            picked.append({"image": image, "heading": heading})
        if len(picked) == per_site:
            break
    photos = []
    for choice in picked:
        image = choice["image"]
        photo_id = f"mly-{image['id']}"
        path = VISION / "photos" / f"{photo_id}.jpg"
        path.write_bytes(get(image["thumb_1024_url"]))
        captured = datetime.fromtimestamp(image["captured_at"] / 1000, timezone.utc).isoformat() if image.get("captured_at") else None
        params = image.get("camera_parameters") or []
        photos.append({"id": photo_id, "kind": "street", "file": str(path.relative_to(VISION)), "mime": "image/jpeg",
                       "coordinate": list(where(image)), "heading": choice["heading"], "panorama": bool(image.get("is_pano")),
                       "focal": params[0] if params else None, "captured_at": captured,
                       "source": f"Mapillary image {image['id']}", "license": "CC BY-SA 4.0",
                       "attribution": f"© {(image.get('creator') or {}).get('username', 'Mapillary contributor')}, Mapillary, CC BY-SA 4.0",
                       "url": f"https://www.mapillary.com/app/?pKey={image['id']}"})
    return photos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-network", action="store_true", help="I authorize free requests to Planetary Computer and Mapillary")
    parser.add_argument("--per-site", type=int, default=3, help="street-level photos per site")
    parser.add_argument("--max-photos", type=int, default=24, help="hard cap on all photos, which is also the Gemini call count")
    parser.add_argument("--no-aerial", action="store_true", help="skip the aerial tiles")
    parser.add_argument("--aerial-size", type=float, default=140, help="meters across each aerial tile")
    # mapillary barely covers the hill (no photos within 45 m of olympic hall),
    # and a photo is placed from its own camera position, so 150 m is fine
    parser.add_argument("--radius", type=float, default=150, help="how far from a site a street photo may be taken")
    args = parser.parse_args()
    if not args.confirm_network:
        raise SystemExit("Pass --confirm-network to fetch photos (free Planetary Computer and Mapillary requests).")
    load_keys()
    token = os.environ.get("MAPILLARY_TOKEN")
    if not token:
        print("No MAPILLARY_TOKEN set, so only aerial photos will be fetched.", file=sys.stderr)

    if not (VISION / "gaps.json").exists():
        raise SystemExit("No gaps.json yet: run scripts/vision_find_gaps.py first.")
    sites = json.loads((VISION / "gaps.json").read_text(encoding="utf-8"))["sites"]
    (VISION / "photos").mkdir(parents=True, exist_ok=True)
    manifest_path = VISION / "photos.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    have = {p["id"] for p in manifest}
    for site in sites:
        if len(manifest) >= args.max_photos:
            break
        print(f"{site['name']}:")
        new = []
        if not args.no_aerial and f"naip-{site['id']}" not in have:
            shot = aerial(site, args.aerial_size, 768)
            new += [shot] if shot else []
        if token:
            try:
                new += [p for p in street(site, token, args.per_site, args.radius) if p["id"] not in have]
            except urllib.error.HTTPError as exc:
                raise SystemExit(f"Mapillary returned {exc.code}; check MAPILLARY_TOKEN") from exc
        for photo in new[:args.max_photos - len(manifest)]:
            photo.update(site_id=site["id"], site_name=site["name"])
            photo.setdefault("coordinate", list(site["coordinate"]))
            manifest.append(photo)
            have.add(photo["id"])
            print(f"  {photo['kind']:6s} {photo['id']}")
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        time.sleep(1)
    print(f"{len(manifest)} photos in {manifest_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
