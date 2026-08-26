"""
Prototype waterbody/coastal buffer violation detection

Usage examples in README.md.

This script:
- Queries Overpass API for water features in a bbox
- Builds metric buffers around those features
- Accepts a project polygon (GeoJSON) or a project point and tests intersections
- Outputs evidence.geojson, report.json, and map.png

Notes:
- Buffering is done in a local UTM projection for reasonable meter-based distances
- This prototype handles 'way' elements returned by Overpass with a 'geometry' list

"""

import argparse
import json
import os
import math
from typing import Tuple, List

import requests
from shapely.geometry import Point, LineString, Polygon, mapping, shape
from shapely.ops import unary_union, transform
try:
    import geopandas as gpd
    HAS_GEOPANDAS = True
except Exception:
    gpd = None
    HAS_GEOPANDAS = False
try:
    from pyproj import CRS, Transformer
    HAS_PYPROJ = True
except Exception:
    CRS = None
    Transformer = None
    HAS_PYPROJ = False
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt


# Prefer a public Overpass mirror — switch if one is unreachable.
# Keep this intentionally short so the API doesn't block the user interface for minutes.
OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"
OVERPASS_TIMEOUT_SECONDS = 20


def parse_bbox(bbox_str: str) -> Tuple[float, float, float, float]:
    parts = [float(x) for x in bbox_str.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be minlon,minlat,maxlon,maxlat")
    return tuple(parts)


def lonlat_to_utm_epsg(lon: float, lat: float) -> int:
    # UTM zone calculation
    zone = int((math.floor((lon + 180) / 6) % 60) + 1)
    if lat >= 0:
        return 32600 + zone
    else:
        return 32700 + zone


def overpass_water_query(bbox: Tuple[float, float, float, float]) -> dict:
    minlon, minlat, maxlon, maxlat = bbox
    # Query common water features including ways and relations (relations often represent multipolygon lakes)
    query = f"""
[out:json][timeout:120];
(
  way["natural"="water"]({minlat},{minlon},{maxlat},{maxlon});
  way["water"="lake"]({minlat},{minlon},{maxlat},{maxlon});
  way["waterway"]({minlat},{minlon},{maxlat},{maxlon});
  way["landuse"="reservoir"]({minlat},{minlon},{maxlat},{maxlon});
  relation["natural"="water"]({minlat},{minlon},{maxlat},{maxlon});
  relation["water"="lake"]({minlat},{minlon},{maxlat},{maxlon});
  relation["landuse"="reservoir"]({minlat},{minlon},{maxlat},{maxlon});
);
out body geom;
"""
    headers = {"User-Agent": "sdgggg-prototype/1.0 (+https://example.com)", "Accept": "application/json"}
    resp = requests.post(OVERPASS_URL, data={"data": query}, headers=headers, timeout=OVERPASS_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json()


def elements_to_geometries(overpass_json: dict) -> List[Tuple[Polygon, dict]]:
    feats = []
    elements = overpass_json.get("elements", [])
    # Build a lookup for way geometries (by id) so relations can reference them
    way_geoms = {}
    for el in elements:
        if el.get("type") == "way" and "geometry" in el:
            coords = [(pt["lon"], pt["lat"]) for pt in el["geometry"]]
            if len(coords) >= 4 and coords[0] == coords[-1]:
                try:
                    geom = Polygon(coords)
                except Exception:
                    geom = LineString(coords)
            else:
                geom = LineString(coords)
            way_geoms[el.get("id")] = (geom, el)
            feats.append((geom, el))

    # Now handle relations (multipolygons) by assembling member ways where available
    for el in elements:
        if el.get("type") == "relation":
            members = el.get("members", [])
            outer_geoms = []
            inner_geoms = []
            other_geoms = []
            for m in members:
                if m.get("type") == "way":
                    ref = m.get("ref")
                    if ref in way_geoms:
                        member_geom, member_meta = way_geoms[ref]
                        role = (m.get("role") or "").lower()
                        if role == "outer":
                            outer_geoms.append(member_geom)
                        elif role == "inner":
                            inner_geoms.append(member_geom)
                        else:
                            # unknown/empty role: treat as outer by default
                            other_geoms.append(member_geom)

            # If we have no assembled member geometries, skip
            if not (outer_geoms or inner_geoms or other_geoms):
                continue

            try:
                # assemble outers — include other_geoms as outers if outers empty
                if outer_geoms:
                    outer_union = unary_union(outer_geoms)
                elif other_geoms:
                    outer_union = unary_union(other_geoms)
                else:
                    outer_union = None

                inner_union = unary_union(inner_geoms) if inner_geoms else None

                final_geom = None
                if outer_union is not None:
                    final_geom = outer_union
                    if inner_union is not None:
                        # subtract inner holes from outer polygons
                        try:
                            final_geom = outer_union.difference(inner_union)
                        except Exception:
                            # fallback to union of all members
                            final_geom = unary_union(outer_geoms + inner_geoms + other_geoms)
                else:
                    # no explicit outer, union everything
                    final_geom = unary_union(outer_geoms + inner_geoms + other_geoms)

                # If final_geom is linework that can be polygonized, try that
                if final_geom.geom_type in ("LineString", "MultiLineString"):
                    from shapely.ops import polygonize
                    polys = list(polygonize(final_geom))
                    if polys:
                        final_geom = unary_union(polys)

                # Attach role-aware metadata for debugging
                rel_meta = dict(el)
                rel_meta.setdefault("assembled_roles", {})
                rel_meta["assembled_roles"]["num_outer"] = len(outer_geoms)
                rel_meta["assembled_roles"]["num_inner"] = len(inner_geoms)
                rel_meta["assembled_roles"]["num_other"] = len(other_geoms)

                feats.append((final_geom, rel_meta))
            except Exception:
                # fallback: skip relation if union fails
                continue

    return feats


def geom_list_to_gdf(geoms_with_meta: List[Tuple], crs="EPSG:4326"):
    """Return a GeoDataFrame when geopandas is available, otherwise return a list of dicts
    with 'geometry' and 'meta' keys.
    """
    if HAS_GEOPANDAS:
        rows = []
        for geom, meta in geoms_with_meta:
            rows.append({"geometry": geom, "meta": meta})
        gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)
        return gdf
    else:
        return [{"geometry": geom, "meta": meta} for geom, meta in geoms_with_meta]


def load_project_geojson(path: str):
    if HAS_GEOPANDAS:
        gdf = gpd.read_file(path)
        if gdf.crs is None:
            gdf.set_crs("EPSG:4326", inplace=True)
        return gdf
    else:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        geoms = []
        if data.get("type") == "FeatureCollection":
            for feat in data.get("features", []):
                geoms.append(shape(feat.get("geometry")))
        elif data.get("type") == "Feature":
            geoms.append(shape(data.get("geometry")))
        else:
            geoms.append(shape(data))
        return geoms


def make_project_from_point(lon: float, lat: float, radius_m: float = 10.0):
    pt = Point(lon, lat)
    if HAS_GEOPANDAS:
        gdf = gpd.GeoDataFrame([{"geometry": pt}], geometry="geometry", crs="EPSG:4326")
        # Reproject to UTM, buffer, project back
        epsg = lonlat_to_utm_epsg(lon, lat)
        gdf_utm = gdf.to_crs(epsg)
        gdf_utm["geometry"] = gdf_utm.geometry.buffer(radius_m)
        return gdf_utm.to_crs("EPSG:4326")
    else:
        if not HAS_PYPROJ:
            # approximate buffer in degrees (very rough fallback)
            approx_deg = radius_m / 111320.0
            return [pt.buffer(approx_deg)]
        utm_epsg = lonlat_to_utm_epsg(lon, lat)
        transformer_to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
        transformer_to_wgs = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
        pt_utm = transform(lambda x, y, z=None: transformer_to_utm.transform(x, y), pt)
        buf_utm = pt_utm.buffer(radius_m)
        buf_wgs = transform(lambda x, y, z=None: transformer_to_wgs.transform(x, y), buf_utm)
        return [buf_wgs]


def project_and_buffer(water_gdf_or_list, buffer_m: float, utm_epsg: int):
    """Return buffered geometries in WGS84. If geopandas is available, return a GeoDataFrame.
    Otherwise return a list of shapely geometries.
    """
    if HAS_GEOPANDAS:
        gdf_utm = water_gdf_or_list.to_crs(utm_epsg)
        gdf_utm_buffered = gdf_utm.copy()
        gdf_utm_buffered["geometry"] = gdf_utm_buffered.geometry.buffer(buffer_m)
        return gdf_utm_buffered.to_crs("EPSG:4326")
    else:
        buffered = []
        if not HAS_PYPROJ:
            approx_deg = buffer_m / 111320.0
            for item in water_gdf_or_list:
                geom = item["geometry"]
                buffered.append(geom.buffer(approx_deg))
            return buffered
        transformer_to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
        transformer_to_wgs = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
        for item in water_gdf_or_list:
            geom = item["geometry"]
            geom_utm = transform(lambda x, y, z=None: transformer_to_utm.transform(x, y), geom)
            buf_utm = geom_utm.buffer(buffer_m)
            buf_wgs = transform(lambda x, y, z=None: transformer_to_wgs.transform(x, y), buf_utm)
            buffered.append(buf_wgs)
        return buffered


def assemble_outputs(water_gdf_or_list, buffer_gdfs: dict, project_gdf_or_list, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    features = []

    # water features
    if HAS_GEOPANDAS:
        for idx, row in water_gdf_or_list.reset_index().iterrows():
            feat = {"type": "Feature", "properties": {"source": "osm", "id": int(idx)}, "geometry": mapping(row.geometry)}
            features.append(feat)
    else:
        for idx, item in enumerate(water_gdf_or_list):
            feat = {"type": "Feature", "properties": {"source": "osm", "id": int(idx)}, "geometry": mapping(item["geometry"])}
            features.append(feat)

    # buffers: include property distance
    for dist, gdfs in buffer_gdfs.items():
        if HAS_GEOPANDAS:
            for idx, row in gdfs.reset_index().iterrows():
                feat = {"type": "Feature", "properties": {"type": "buffer", "distance_m": float(dist), "id": int(idx)}, "geometry": mapping(row.geometry)}
                features.append(feat)
        else:
            for idx, geom in enumerate(gdfs):
                feat = {"type": "Feature", "properties": {"type": "buffer", "distance_m": float(dist), "id": int(idx)}, "geometry": mapping(geom)}
                features.append(feat)

    # project polygon(s)
    if HAS_GEOPANDAS:
        for idx, row in project_gdf_or_list.reset_index().iterrows():
            feat = {"type": "Feature", "properties": {"type": "project", "id": int(idx)}, "geometry": mapping(row.geometry)}
            features.append(feat)
    else:
        for idx, geom in enumerate(project_gdf_or_list):
            feat = {"type": "Feature", "properties": {"type": "project", "id": int(idx)}, "geometry": mapping(geom)}
            features.append(feat)

    fc = {"type": "FeatureCollection", "features": features}

    # If an EC parse result exists in out_dir, include it in the FeatureCollection properties for auditing
    ec_parse_file = os.path.join(out_dir, "ec_parse.json")
    if os.path.exists(ec_parse_file):
        try:
            with open(ec_parse_file, "r", encoding="utf-8") as ef:
                ec_parse = json.load(ef)
            fc["properties"] = {"ec_parse": ec_parse}
        except Exception:
            # ignore read errors and leave fc without properties
            pass

    geojson_path = os.path.join(out_dir, "evidence.geojson")
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(fc, f)

    print(f"Wrote evidence GeoJSON to {geojson_path}")


def _plot_geom(ax, geom, **kwargs):
    # handle Polygon, LineString, Point
    if geom is None:
        return
    geom_type = geom.geom_type
    if geom_type == "Polygon":
        xs, ys = geom.exterior.xy
        ax.fill(xs, ys, **kwargs)
    elif geom_type == "MultiPolygon":
        for part in geom.geoms:
            xs, ys = part.exterior.xy
            ax.fill(xs, ys, **kwargs)
    elif geom_type == "LineString":
        xs, ys = geom.xy
        ax.plot(xs, ys, **kwargs)
    elif geom_type == "Point":
        x, y = geom.x, geom.y
        ax.plot(x, y, marker='o', **kwargs)


def plot_map(water_gdf_or_list, buffer_gdfs: dict, project_gdf_or_list, out_dir: str):
    try:
        import contextily as cx
    except Exception:
        cx = None

    if HAS_GEOPANDAS and cx is not None and hasattr(water_gdf_or_list, "to_crs"):
        fig, ax = plt.subplots(figsize=(8, 8))
        water_3857 = water_gdf_or_list.to_crs("EPSG:3857") if not water_gdf_or_list.empty else water_gdf_or_list
        project_3857 = project_gdf_or_list.to_crs("EPSG:3857") if not project_gdf_or_list.empty else project_gdf_or_list

        if not water_3857.empty:
            water_3857.plot(ax=ax, color="#8ecae6", edgecolor="#1d3557", linewidth=1.0, alpha=0.9)

        for dist, gdfs in sorted(buffer_gdfs.items()):
            gdfs_3857 = gdfs.to_crs("EPSG:3857") if hasattr(gdfs, "to_crs") else gdfs
            gdfs_3857.plot(ax=ax, facecolor="#f4a261", edgecolor="#7f4f24", alpha=0.35)

        if not project_3857.empty:
            project_3857.plot(ax=ax, facecolor="none", edgecolor="#06d6a0", linewidth=2.5)

        xmin, ymin, xmax, ymax = water_3857.total_bounds if not water_3857.empty else project_3857.total_bounds
        if hasattr(project_3857, "total_bounds"):
            proj_bounds = project_3857.total_bounds
            xmin = min(xmin, proj_bounds[0]) if not water_3857.empty else proj_bounds[0]
            ymin = min(ymin, proj_bounds[1]) if not water_3857.empty else proj_bounds[1]
            xmax = max(xmax, proj_bounds[2]) if not water_3857.empty else proj_bounds[2]
            ymax = max(ymax, proj_bounds[3]) if not water_3857.empty else proj_bounds[3]

        pad = 200
        ax.set_xlim(xmin - pad, xmax + pad)
        ax.set_ylim(ymin - pad, ymax + pad)
        ax.set_axis_off()
        try:
            cx.add_basemap(ax, crs="EPSG:3857", source=cx.providers.Esri.WorldImagery, attribution=False)
        except Exception:
            pass
        plt.tight_layout()
        path = os.path.join(out_dir, "map.png")
        plt.savefig(path, dpi=180, bbox_inches='tight')
        plt.close()
        print(f"Wrote map to {path}")
        return

    fig, ax = plt.subplots(figsize=(8, 8))
    if HAS_GEOPANDAS:
        if not water_gdf_or_list.empty:
            for geom in water_gdf_or_list.geometry:
                _plot_geom(ax, geom, color="#6baed6", linewidth=0.6)
    else:
        for item in water_gdf_or_list:
            _plot_geom(ax, item["geometry"], color="#6baed6", linewidth=0.6)

    colors = ["#fee391", "#fdae6b", "#e6550d", "#a63603"]
    for i, (dist, gdfs) in enumerate(sorted(buffer_gdfs.items())):
        color = colors[i % len(colors)]
        if HAS_GEOPANDAS:
            for geom in gdfs.geometry:
                _plot_geom(ax, geom, facecolor=color, edgecolor="#7f2704", alpha=0.4)
        else:
            for geom in gdfs:
                _plot_geom(ax, geom, facecolor=color, edgecolor="#7f2704", alpha=0.4)

    if HAS_GEOPANDAS:
        for geom in project_gdf_or_list.geometry:
            _plot_geom(ax, geom, facecolor="none", edgecolor="#238b45", linewidth=2)
    else:
        for geom in project_gdf_or_list:
            _plot_geom(ax, geom, facecolor="none", edgecolor="#238b45", linewidth=2)

    ax.set_axis_off()
    plt.tight_layout()
    path = os.path.join(out_dir, "map.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"Wrote map to {path}")


def detect_violations(buffer_gdfs: dict, project_gdf_or_list, water_gdf_or_list=None, water_source: str = "overpass") -> dict:
    report = {"violations": [], "summary": {}, "issues": [], "findings": [], "data_quality": {"water_source": water_source, "project_input": "geojson" if HAS_GEOPANDAS and hasattr(project_gdf_or_list, "geometry") else "point_or_polygon"}}
    total_water_features = 0
    if water_gdf_or_list is not None:
        if HAS_GEOPANDAS:
            total_water_features = len(water_gdf_or_list)
        else:
            total_water_features = len(water_gdf_or_list)
    report["data_quality"]["water_feature_count"] = total_water_features

    hit_count = 0
    for dist, gdfs in sorted(buffer_gdfs.items()):
        intersects = False
        num_intersections = 0
        if HAS_GEOPANDAS:
            for buf_geom in gdfs.geometry:
                for proj_geom in project_gdf_or_list.geometry:
                    if buf_geom.intersects(proj_geom):
                        intersects = True
                        num_intersections += 1
        else:
            for buf_geom in gdfs:
                for proj_geom in project_gdf_or_list:
                    if buf_geom.intersects(proj_geom):
                        intersects = True
                        num_intersections += 1
        if intersects:
            hit_count += 1
        report_entry = {"buffer_m": float(dist), "intersects": intersects, "num_intersections": num_intersections}
        report["violations"].append(report_entry)

        if intersects:
            report["findings"].append({
                "buffer_m": float(dist),
                "risk": "high" if num_intersections > 0 else "moderate",
                "message": f"Project intersects the {dist} m protected water buffer in {num_intersections} area(s).",
            })

    if water_source == "synthetic_fallback":
        report["issues"].append("Overpass water-data retrieval failed, so the analysis used a synthetic fallback water geometry. This can create a false positive and should be treated as a demo-level result, not a verified field assessment.")
    if hit_count == 0:
        report["issues"].append("No direct intersection was detected within the tested buffers. This does not guarantee compliance; it only means the project footprint did not overlap the detected water buffers in this simplified analysis.")
    else:
        report["issues"].append("At least one tested buffer zone intersects the project footprint. Treat this as a likely compliance issue requiring document review and a field verification check.")

    report["summary"] = {
        "violations_found": hit_count,
        "tested_buffers_m": [float(dist) for dist in sorted(buffer_gdfs.keys())],
        "status": "likely_violation" if hit_count > 0 else "no_direct_violation_detected",
        "confidence": "low" if water_source == "synthetic_fallback" else "medium",
    }
    return report


def run_detection(bbox: Tuple[float, float, float, float], project_geojson_path: str = None, project_point: Tuple[float, float] = None, buffers: List[float] = [30.0, 50.0, 100.0], out_dir: str = "outputs", enable_ndwi: bool = False, ndwi_dates: Tuple[str, str] = (None, None)):
    """Run the detection pipeline programmatically and return a dict with report and paths.

    Parameters:
    - bbox: (minlon, minlat, maxlon, maxlat)
    - project_geojson_path: optional path to a GeoJSON file
    - project_point: optional (lon, lat) tuple
    - buffers: list of buffer distances in meters
    - out_dir: output directory

    Returns: dict with keys: report (dict), report_path, evidence_path, map_path
    """
    bbox_vals = bbox if isinstance(bbox, tuple) else tuple(bbox)
    print(f"Querying Overpass for bbox: {bbox_vals}")
    water_source = "overpass"
    try:
        overpass_json = overpass_water_query(bbox_vals)
        geoms_meta = elements_to_geometries(overpass_json)
        water_gdf = geom_list_to_gdf(geoms_meta)
    except Exception as e:
        water_source = "synthetic_fallback"
        print(f"Overpass query failed: {e}. Falling back to a synthetic test water geometry.")
        # synthetic polygon near the project point (small test lake)
        poly = Polygon([(bbox_vals[0]+0.010, bbox_vals[1]+0.008),(bbox_vals[0]+0.014, bbox_vals[1]+0.008),(bbox_vals[0]+0.014, bbox_vals[1]+0.011),(bbox_vals[0]+0.010, bbox_vals[1]+0.011),(bbox_vals[0]+0.010, bbox_vals[1]+0.008)])
        geoms_meta = [(poly, {"synthetic": True})]
        water_gdf = geom_list_to_gdf(geoms_meta)

    # determine UTM EPSG from bbox centroid
    center_lon = (bbox_vals[0] + bbox_vals[2]) / 2.0
    center_lat = (bbox_vals[1] + bbox_vals[3]) / 2.0
    utm_epsg = lonlat_to_utm_epsg(center_lon, center_lat)
    print(f"Using UTM EPSG:{utm_epsg} for metric buffering")

    # prepare project geometry
    if project_geojson_path:
        project_gdf = load_project_geojson(project_geojson_path)
    elif project_point:
        lon, lat = project_point
        project_gdf = make_project_from_point(lon, lat, radius_m=10.0)
    else:
        raise ValueError("Either project_geojson_path or project_point must be provided")

    # prepare buffer gdfs
    buffer_gdfs = {}
    for dist in buffers:
        buf_gdf = project_and_buffer(water_gdf, dist, utm_epsg)
        buffer_gdfs[dist] = buf_gdf

    # detection
    report = detect_violations(buffer_gdfs, project_gdf, water_gdf_or_list=water_gdf, water_source=water_source)
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote report to {report_path}")

    evidence_path = os.path.join(out_dir, "evidence.geojson")
    assemble_outputs(water_gdf, buffer_gdfs, project_gdf, out_dir)
    plot_map(water_gdf, buffer_gdfs, project_gdf, out_dir)

    result = {"report": report, "report_path": report_path, "evidence_path": evidence_path, "map_path": os.path.join(out_dir, "map.png")}

    # optional NDWI generation via Google Earth Engine
    if enable_ndwi:
        try:
            from ee_ndwi import compute_ndwi
            sd, ed = ndwi_dates if ndwi_dates is not None else (None, None)
            ndwi_out = os.path.join(out_dir, "ndwi.png")
            compute_ndwi(bbox_vals, ndwi_out, start_date=sd, end_date=ed)
            result["ndwi_path"] = ndwi_out
        except Exception as e:
            # don't fail the whole run for missing EE creds — include the message in the result
            result["ndwi_error"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(description="Prototype waterbody buffer violation detection")
    parser.add_argument("--bbox", type=str, help="minlon,minlat,maxlon,maxlat (required)")
    parser.add_argument("--project-geojson", type=str, help="Path to project GeoJSON polygon (optional)")
    parser.add_argument("--project-point", type=str, help="lon,lat (optional)")
    parser.add_argument("--buffers", type=float, nargs="*", default=[30.0, 50.0, 100.0], help="Buffer distances in meters")
    parser.add_argument("--out-dir", type=str, default="outputs", help="Output directory")
    args = parser.parse_args()

    if not args.bbox:
        parser.error("--bbox is required")

    bbox = parse_bbox(args.bbox)
    proj_geojson = args.project_geojson
    proj_point = None
    if args.project_point:
        lon, lat = [float(x) for x in args.project_point.split(",")]
        proj_point = (lon, lat)

    run_detection(bbox, project_geojson_path=proj_geojson, project_point=proj_point, buffers=args.buffers, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
