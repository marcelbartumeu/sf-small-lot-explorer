"""
make_slim.py — stream all active SF parcels from the DataSF API,
measure each parcel's width and length, and write docs/lots.geojson.

No pre-filter — every active measured parcel is included so the browser
viewer can filter freely (blank limits = show everything).

Uses the Socrata GeoJSON resource API with pagination (5 000 rows/page).
"""

from __future__ import annotations

import json, math, sys, urllib.request
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape, MultiPolygon, Polygon
from shapely.ops import transform as shp_transform

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE  = "https://data.sfgov.org/resource/acdm-wktn.geojson"
PAGE_SIZE = 5_000
OUT       = Path(__file__).resolve().parent / "docs" / "lots.geojson"

TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:2227", always_xy=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def project(geom):
    return shp_transform(lambda x, y, z=None: TRANSFORMER.transform(x, y), geom)

def rect_dims(geom) -> tuple[float, float]:
    try:
        mrr   = geom.minimum_rotated_rectangle
        pts   = list(mrr.exterior.coords)
        sides = sorted(math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]) for i in range(4))
        return (sides[0]+sides[1])/2, (sides[2]+sides[3])/2
    except Exception:
        return 0.0, 0.0

def round_coords(c, dp=5):
    if isinstance(c[0], (list, tuple)):
        return [round_coords(x, dp) for x in c]
    return [round(float(c[0]), dp), round(float(c[1]), dp)]

def fetch_page(offset: int) -> list:
    url = (f"{API_BASE}?$where=active=true"
           f"&$limit={PAGE_SIZE}&$offset={offset}"
           f"&$order=:id")
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read())
    return data.get("features", [])

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    features_out = []
    offset = 0
    total_fetched = measured = skipped = 0

    print("Streaming parcels from DataSF API …", flush=True)

    while True:
        print(f"  page offset={offset:,} …", end=" ", flush=True)
        page = fetch_page(offset)
        if not page:
            print("done.")
            break
        print(f"{len(page)} rows", flush=True)

        for feat in page:
            total_fetched += 1
            props = feat.get("properties") or {}

            try:
                geom  = shape(feat["geometry"])
                # Simplify in WGS84 before projecting — 0.000035° ≈ 3 m, invisible at parcel scale
                geom  = geom.simplify(0.000035, preserve_topology=True)
                pgeom = project(geom)
                if isinstance(pgeom, MultiPolygon):
                    pgeom = max(pgeom.geoms, key=lambda g: g.area)
                if not isinstance(pgeom, Polygon) or pgeom.is_empty:
                    skipped += 1; continue
                w, l = rect_dims(pgeom)
                if w <= 0:
                    skipped += 1; continue
            except Exception:
                skipped += 1; continue

            # Re-export the simplified WGS84 geometry (not the projected one)
            geom_dict = {"type": geom.geom_type,
                         "coordinates": round_coords(
                             list(geom.exterior.coords) if geom.geom_type == "Polygon"
                             else [list(p.exterior.coords) for p in geom.geoms]
                         )}
            # Ensure proper GeoJSON polygon structure
            if geom.geom_type == "Polygon":
                geom_dict["coordinates"] = [round_coords(list(geom.exterior.coords))]

            features_out.append({
                "type": "Feature",
                "geometry": geom_dict,
                "properties": {
                    "b":  str(props.get("blklot", "") or ""),
                    "fa": str(props.get("from_address_num", "") or ""),
                    "ta": str(props.get("to_address_num", "") or ""),
                    "sn": str(props.get("street_name", "") or ""),
                    "st": str(props.get("street_type", "") or ""),
                    "z":  str(props.get("zoning_code", "") or "").strip(),
                    "n":  str(props.get("analysis_neighborhood", "") or "").strip(),
                    "sd": str(props.get("supervisor_district", "") or ""),
                    "w":  round(w, 1),
                    "l":  round(l, 1),
                },
            })
            measured += 1

        offset += PAGE_SIZE

    print(f"\nFetched : {total_fetched:,} active parcels")
    print(f"Measured: {measured:,}")
    print(f"Skipped : {skipped:,}")
    print(f"\nWriting {OUT} …", flush=True)

    with open(OUT, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": features_out},
                  fh, separators=(",", ":"))

    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"Done — {measured:,} features, {size_mb:.1f} MB")

if __name__ == "__main__":
    main()
