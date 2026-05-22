"""Read matching_broad.geojson and write a slim version for the browser app.

- Rounds coordinates to 6 decimals (~10 cm, more than enough at parcel scale).
- Keeps only the props the UI uses.
- Writes a compact single-line JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "matching_broad.geojson"
DST = HERE / "viewer" / "lots.geojson"

KEEP_PROPS = {
    "blklot": "b",
    "from_address_num": "fa",
    "to_address_num": "ta",
    "street_name": "sn",
    "street_type": "st",
    "zoning_code": "z",
    "analysis_neighborhood": "n",
    "supervisor_district": "sd",
    "measured_width_ft": "w",
    "measured_length_ft": "l",
    "measured_area_sqft": "a",
}


def round_coords(coords):
    if isinstance(coords[0], (list, tuple)):
        return [round_coords(c) for c in coords]
    return [round(coords[0], 6), round(coords[1], 6)]


def main() -> None:
    DST.parent.mkdir(parents=True, exist_ok=True)
    with open(SRC) as fh:
        data = json.load(fh)

    out_features = []
    for feat in data["features"]:
        props = feat.get("properties") or {}
        slim_props = {short: props.get(long) for long, short in KEEP_PROPS.items()}
        geom = feat["geometry"]
        geom["coordinates"] = round_coords(geom["coordinates"])
        out_features.append({"type": "Feature", "geometry": geom, "properties": slim_props})

    out = {"type": "FeatureCollection", "features": out_features}
    with open(DST, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))

    size_mb = DST.stat().st_size / 1024 / 1024
    print(f"wrote {DST}  ({len(out_features):,} features, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
