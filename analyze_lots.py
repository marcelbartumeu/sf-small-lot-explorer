"""
SFO single-stair lot analyzer.

Streams the SF Parcels GeoJSON, projects to California State Plane Zone 3
(EPSG:2227, US Survey Feet), and measures each parcel's width and length via
the minimum rotated rectangle (so orientation relative to the street doesn't
matter).

Filters:
  - "ideal"  ~ 25' x 100'   ->  width in [24, 26],  length in [95, 105]
  - "broad"  flexible band  ->  width in [24, 30],  length in [80, 120]

Outputs (written next to this script):
  - report.md
  - matching_broad.csv
  - matching_broad.geojson
  - matching_ideal.csv
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"not serializable: {type(obj).__name__}")

import ijson
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform as shp_transform

GEOJSON_PATH = Path(
    "/Users/marcelbartumeu/Desktop/Parcels_–_Active_and_Retired_20260522.geojson"
)
OUT_DIR = Path(__file__).resolve().parent

# WGS84 -> NAD83 / California zone 3 (US Survey Feet). SF is in zone 3.
TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:2227", always_xy=True)


def project(geom):
    return shp_transform(lambda x, y, z=None: TRANSFORMER.transform(x, y), geom)


def rect_dims_ft(geom) -> tuple[float, float, float]:
    """Return (width_ft, length_ft, area_sqft) using the minimum rotated rectangle.

    Width = shorter side, length = longer side.
    """
    if geom.is_empty:
        return 0.0, 0.0, 0.0
    mrr = geom.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)
    # 4 distinct corners + closing point
    sides = []
    for i in range(4):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        sides.append(math.hypot(x2 - x1, y2 - y1))
    # opposite sides should match in pairs; pick the two distinct lengths
    sides.sort()
    short = (sides[0] + sides[1]) / 2.0
    long_ = (sides[2] + sides[3]) / 2.0
    return short, long_, geom.area


def in_band(w: float, l: float, w_lo: float, w_hi: float, l_lo: float, l_hi: float) -> bool:
    return w_lo <= w <= w_hi and l_lo <= l <= l_hi


# Residential zoning prefixes most relevant to single-stair small-lot multifamily.
RESIDENTIAL_PREFIXES = ("RH", "RM", "RTO", "RC", "NCT", "NC")


def is_residentialish(zoning_code: str | None) -> bool:
    if not zoning_code:
        return False
    z = zoning_code.upper()
    return any(z.startswith(p) for p in RESIDENTIAL_PREFIXES)


def main() -> None:
    total = 0
    active_total = 0
    measured = 0
    broad_hits = []
    ideal_hits = []

    by_zoning_total: Counter[str] = Counter()
    by_zoning_broad: Counter[str] = Counter()
    by_zoning_ideal: Counter[str] = Counter()
    by_nb_total: Counter[str] = Counter()
    by_nb_broad: Counter[str] = Counter()
    by_nb_ideal: Counter[str] = Counter()

    # Sanity: also count residential-only subset for fairer "% of buildable lots"
    residential_total = 0
    residential_broad = 0
    residential_ideal = 0

    with open(GEOJSON_PATH, "rb") as fh:
        for feat in ijson.items(fh, "features.item"):
            total += 1
            props = feat.get("properties") or {}
            if not props.get("active"):
                continue
            active_total += 1

            try:
                geom = shape(feat["geometry"])
            except Exception:
                continue
            if geom.is_empty:
                continue

            try:
                pgeom = project(geom)
            except Exception:
                continue

            # Some parcels are MultiPolygons (split parcels). Measure largest piece.
            if isinstance(pgeom, MultiPolygon):
                pgeom = max(pgeom.geoms, key=lambda g: g.area)
            if not isinstance(pgeom, Polygon):
                continue

            try:
                w, l, area = rect_dims_ft(pgeom)
            except Exception:
                continue
            if w <= 0 or l <= 0:
                continue

            measured += 1
            zoning = (props.get("zoning_code") or "UNKNOWN").strip() or "UNKNOWN"
            nb = (props.get("analysis_neighborhood") or "Unknown").strip() or "Unknown"
            by_zoning_total[zoning] += 1
            by_nb_total[nb] += 1
            res_ish = is_residentialish(zoning)
            if res_ish:
                residential_total += 1

            broad = in_band(w, l, 24, 30, 80, 120)
            ideal = in_band(w, l, 24, 26, 95, 105)

            if broad:
                by_zoning_broad[zoning] += 1
                by_nb_broad[nb] += 1
                if res_ish:
                    residential_broad += 1
                broad_hits.append((feat, props, w, l, area))
            if ideal:
                by_zoning_ideal[zoning] += 1
                by_nb_ideal[nb] += 1
                if res_ish:
                    residential_ideal += 1
                ideal_hits.append((feat, props, w, l, area))

            if measured % 25000 == 0:
                print(
                    f"  ... measured {measured:,}  broad={len(broad_hits):,}  ideal={len(ideal_hits):,}",
                    file=sys.stderr,
                )

    # ---------- write outputs ----------
    def write_csv(path: Path, rows):
        with open(path, "w", newline="") as out:
            w = csv.writer(out)
            w.writerow(
                [
                    "blklot",
                    "address",
                    "street",
                    "zoning_code",
                    "zoning_district",
                    "neighborhood",
                    "supervisor_district",
                    "width_ft",
                    "length_ft",
                    "area_sqft",
                ]
            )
            for _feat, props, width, length, area in rows:
                addr_from = props.get("from_address_num") or ""
                addr_to = props.get("to_address_num") or ""
                addr = addr_from if addr_from == addr_to or not addr_to else f"{addr_from}-{addr_to}"
                street = " ".join(
                    str(p) for p in [props.get("street_name"), props.get("street_type")] if p
                )
                w.writerow(
                    [
                        props.get("blklot", ""),
                        addr,
                        street,
                        props.get("zoning_code", ""),
                        props.get("zoning_district", ""),
                        props.get("analysis_neighborhood", ""),
                        props.get("supervisor_district", ""),
                        f"{width:.1f}",
                        f"{length:.1f}",
                        f"{area:.0f}",
                    ]
                )

    write_csv(OUT_DIR / "matching_broad.csv", broad_hits)
    write_csv(OUT_DIR / "matching_ideal.csv", ideal_hits)

    # GeoJSON of broad matches — keeps original WGS84 geometry for easy mapping.
    fc = {"type": "FeatureCollection", "features": []}
    for feat, props, width, length, area in broad_hits:
        out_props = dict(props)
        out_props["measured_width_ft"] = round(width, 1)
        out_props["measured_length_ft"] = round(length, 1)
        out_props["measured_area_sqft"] = round(area, 0)
        fc["features"].append(
            {"type": "Feature", "geometry": feat["geometry"], "properties": out_props}
        )
    with open(OUT_DIR / "matching_broad.geojson", "w") as out:
        json.dump(fc, out, default=_json_default)

    # ---------- report ----------
    def pct(n, d):
        return f"{(100.0 * n / d):.2f}%" if d else "n/a"

    lines = []
    lines.append("# SF parcels — single-stair-eligible small lots\n")
    lines.append(f"Source: `{GEOJSON_PATH.name}`\n")
    lines.append("## Totals\n")
    lines.append(f"- Features in file: **{total:,}**")
    lines.append(f"- Active parcels: **{active_total:,}**")
    lines.append(f"- Measured (active w/ valid polygon): **{measured:,}**")
    lines.append("")
    lines.append("Dimensions come from each parcel's *minimum rotated rectangle* "
                 "projected to EPSG:2227 (California State Plane Zone 3, US Survey Feet). "
                 "Width = shorter side, length = longer side. Multi-polygon parcels are "
                 "measured by their largest component.\n")
    lines.append("## Filter bands\n")
    lines.append("| Band | Width (ft) | Length (ft) | Matching lots | % of measured | % of residential* |")
    lines.append("|---|---|---|---|---|---|")
    lines.append(
        f"| Ideal (~25×100) | 24–26 | 95–105 | **{len(ideal_hits):,}** | "
        f"{pct(len(ideal_hits), measured)} | {pct(residential_ideal, residential_total)} |"
    )
    lines.append(
        f"| Flexible | 24–30 | 80–120 | **{len(broad_hits):,}** | "
        f"{pct(len(broad_hits), measured)} | {pct(residential_broad, residential_total)} |"
    )
    lines.append("")
    lines.append(
        f"\\* Residential = zoning code starting with one of {', '.join(RESIDENTIAL_PREFIXES)} "
        f"({residential_total:,} parcels)."
    )
    lines.append("")

    lines.append("## Flexible-band matches by zoning (top 15)\n")
    lines.append("| Zoning | Matches | Total in zoning | Share of zoning |")
    lines.append("|---|---:|---:|---:|")
    for z, n in by_zoning_broad.most_common(15):
        t = by_zoning_total[z]
        lines.append(f"| {z} | {n:,} | {t:,} | {pct(n, t)} |")
    lines.append("")

    lines.append("## Flexible-band matches by neighborhood (top 20)\n")
    lines.append("| Neighborhood | Matches | Total in neighborhood | Share |")
    lines.append("|---|---:|---:|---:|")
    for nb, n in by_nb_broad.most_common(20):
        t = by_nb_total[nb]
        lines.append(f"| {nb} | {n:,} | {t:,} | {pct(n, t)} |")
    lines.append("")

    lines.append("## Files\n")
    lines.append("- `matching_broad.csv` — all parcels in the flexible band")
    lines.append("- `matching_broad.geojson` — same, ready for QGIS/geojson.io")
    lines.append("- `matching_ideal.csv` — the tight ~25×100 subset")
    lines.append("")

    (OUT_DIR / "report.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
