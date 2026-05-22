# SF Small-Lot Explorer

An interactive map identifying San Francisco parcels potentially eligible for small-multifamily development under **Single Stair Code Reform** — which would allow multi-family buildings on lots too narrow for traditional dual-egress stair configurations.

The target lot type is roughly **25 ft wide × 100 ft long**, the standard SF Victorian-era street grid parcel. The analysis uses a flexible search band of **24–30 ft wide × 80–120 ft long**.

---

## Results

| Band | Width | Length | Lots | % of residential-zoned lots |
|---|---|---|---:|---:|
| Ideal ~25×100 | 24–26 ft | 95–105 ft | **29,701** | 15.7% |
| Flexible | 24–30 ft | 80–120 ft | **63,119** | 33.3% |

**1 in 3 residentially-zoned SF lots** falls in the flexible band. The highest concentrations are in Excelsior, Noe Valley, Outer Mission, Visitacion Valley, Outer Richmond, and Sunset/Parkside.

The denominator is **189,636 residential-zoned lots** (zoning codes starting with RH, RM, RTO, RC, NC, NCT). The full parcel dataset contains 226,637 active parcels, but the remainder are parks, public facilities, commercial and industrial sites, and other land that is not a candidate for small-lot residential development.

---

## Data source

**SF Assessor Parcel Map** — Active and Retired parcels  
Downloaded from [SF Open Data](https://data.sfgov.org) on 2026-05-22 as `Parcels_–_Active_and_Retired_20260522.geojson` (~376 MB).

---

## Methodology

Each parcel's width and length are measured from its **minimum rotated rectangle** (MRR) — the tightest bounding rectangle at any angle — so the result is independent of street orientation.

Geometry is projected from WGS84 to **EPSG:2227** (NAD83 / California State Plane Zone 3, US Survey Feet) before measurement, giving dimensions directly in feet.

For multi-polygon parcels (e.g. split lots), only the largest component is measured.

The filter is purely geometric and does not account for height limits, setback requirements, existing structures, lot mergers, or pending permits. Treat results as the **upper bound** of the eligible pool.

---

## Reproduce the analysis

### Requirements

- Python 3.10+
- Dependencies: `shapely`, `pyproj`, `ijson`

```bash
cd "SFO PLOTS"
python3 -m venv .venv
source .venv/bin/activate
pip install shapely pyproj ijson
```

### Step 1 — Run the analysis

Place the downloaded GeoJSON at the path in `analyze_lots.py` (or edit the `GEOJSON_PATH` constant), then:

```bash
python3 analyze_lots.py
```

Outputs written to `SFO PLOTS/`:
- `report.md` — full breakdown by zoning and neighborhood
- `matching_broad.csv` — 63,119 flexible-band lots
- `matching_ideal.csv` — 29,701 tight ~25×100 lots
- `matching_broad.geojson` — polygons ready for QGIS / kepler.gl

Runtime: ~35 seconds on Apple Silicon.

### Step 2 — Build the viewer data

```bash
python3 make_slim.py
```

This strips the 98 MB `matching_broad.geojson` down to a 22 MB `docs/lots.geojson` suitable for browser loading (rounded coordinates, minimal properties).

---

## Launch the viewer locally

```bash
cd "SFO PLOTS/docs"
python3 -m http.server 8765
```

Then open **http://localhost:8765/** in your browser.

> The viewer must be served over HTTP (not opened directly as a file) because it fetches `lots.geojson` at runtime.

### What the viewer does

- Renders all ~63k matching parcels as polygons on a Leaflet map (canvas renderer)
- Width and length inputs let you narrow the filter live
- **Flexible** and **Ideal ~25×100** presets for quick comparison
- Neighborhood and zoning dropdowns, auto-populated with per-bucket counts
- Live count and % of all measured parcels
- Width × length heatmap showing the distribution of whatever is currently filtered
- Click any parcel for address, block-lot, dimensions, area, zoning, neighborhood, and supervisor district
