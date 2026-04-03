import os
import json
import numpy as np
import rasterio
from rasterio.transform import rowcol
from rasterio.mask import mask as rio_mask
from shapely.geometry import Point, shape, mapping
import pyproj
from pysheds.grid import Grid
from geopy.geocoders import Nominatim
from dem_downloader import download_dem, download_dem_for_bbox


def get_polygon_geometry(geojson: dict):
    """Extract raw geometry from any GeoJSON type."""
    if geojson.get("type") == "Polygon":
        return geojson
    elif geojson.get("type") == "Feature":
        return geojson["geometry"]
    elif geojson.get("type") == "FeatureCollection":
        return geojson["features"][0]["geometry"]
    raise ValueError(f"Unsupported GeoJSON type: {geojson.get('type')}")


def get_polygon_bbox(geojson: dict):
    geom = shape(get_polygon_geometry(geojson))
    bounds = geom.bounds  # (minx, miny, maxx, maxy)
    padding = 0.05
    return {
        "south": bounds[1] - padding,
        "north": bounds[3] + padding,
        "west": bounds[0] - padding,
        "east": bounds[2] + padding,
        "center_lat": (bounds[1] + bounds[3]) / 2,
        "center_lon": (bounds[0] + bounds[2]) / 2,
    }


def get_polygon_centroid(geojson: dict):
    geom = shape(get_polygon_geometry(geojson))
    centroid = geom.centroid
    return centroid.y, centroid.x


def clip_dem_to_polygon(dem_path: str, geojson: dict, output_path: str):
    """Clip DEM to polygon — handles all GeoJSON types."""
    geometry = get_polygon_geometry(geojson)
    
    with rasterio.open(dem_path) as src:
        clipped, transform = rio_mask(src, [geometry], crop=True, nodata=-9999)
        profile = src.profile.copy()
        profile.update({
            "height": clipped.shape[1],
            "width": clipped.shape[2],
            "transform": transform,
            "nodata": -9999
        })

    os.makedirs(os.path.dirname(output_path) or "data/dem", exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(clipped)
    return output_path


def get_coordinates(place_name: str):
    geolocator = Nominatim(user_agent="flood-risk-agent")
    location = geolocator.geocode(f"{place_name}, India")
    if not location:
        raise ValueError(f"Could not locate: {place_name}")
    return {
        "lat": location.latitude,
        "lon": location.longitude,
        "display_name": location.address
    }


def query_elevation(lat: float, lon: float, dem_path: str):
    with rasterio.open(dem_path) as src:
        row, col = rowcol(src.transform, lon, lat)
        elevation = src.read(1)[row, col]
    return {"elevation_m": float(elevation), "lat": lat, "lon": lon}


def query_elevation_stats(dem_path: str):
    """Get min/max/mean elevation from a clipped DEM."""
    with rasterio.open(dem_path) as src:
        data = src.read(1)
        nodata = src.nodata or -9999
        valid = data[data != nodata]
    return {
        "elevation_min_m": float(valid.min()),
        "elevation_max_m": float(valid.max()),
        "elevation_mean_m": float(valid.mean()),
        "elevation_m": float(valid.mean())  # for compatibility
    }


def analyze_watershed(dem_path: str, lat: float, lon: float):
    grid = Grid.from_raster(dem_path)
    dem = grid.read_raster(dem_path)

    pit_filled = grid.fill_pits(dem)
    flooded = grid.fill_depressions(pit_filled)
    inflated = grid.resolve_flats(flooded)

    fdir = grid.flowdir(inflated)
    acc = grid.accumulation(fdir)

    x, y = lon, lat
    try:
        snap_x, snap_y = grid.snap_to_mask(acc > 1000, (x, y))
    except Exception:
        snap_x, snap_y = x, y

    catch = grid.catchment(x=snap_x, y=snap_y, fdir=fdir, xytype='coordinate')
    catchment_area_km2 = float(catch.sum() * (30 * 30) / 1e6)

    return {
        "catchment_area_km2": round(catchment_area_km2, 2),
        "snap_lat": snap_y,
        "snap_lon": snap_x,
        "flow_accumulation_at_site": float(acc[grid.nearest_cell(x, y)])
    }


def calculate_flood_risk(elevation_m: float, catchment_area_km2: float, flow_accumulation: float):
    if elevation_m < 10:
        elev_score = 40
    elif elevation_m < 50:
        elev_score = 30
    elif elevation_m < 100:
        elev_score = 15
    else:
        elev_score = 5

    if catchment_area_km2 > 500:
        catch_score = 35
    elif catchment_area_km2 > 100:
        catch_score = 25
    elif catchment_area_km2 > 10:
        catch_score = 15
    else:
        catch_score = 5

    if flow_accumulation > 10000:
        flow_score = 25
    elif flow_accumulation > 1000:
        flow_score = 15
    else:
        flow_score = 5

    total = elev_score + catch_score + flow_score
    risk_level = "High" if total >= 70 else "Moderate" if total >= 40 else "Low"

    return {
        "risk_score": total,
        "risk_level": risk_level,
        "elevation_contribution": elev_score,
        "catchment_contribution": catch_score,
        "flow_contribution": flow_score
    }


def full_site_analysis(place_name: str):
    """City name based analysis — existing flow."""
    print(f"Analysing flood risk for: {place_name}")
    coords = get_coordinates(place_name)
    lat, lon = coords["lat"], coords["lon"]

    city = place_name.split(",")[0].strip()
    dem_path, _ = download_dem(city)

    elev = query_elevation(lat, lon, dem_path)
    watershed = analyze_watershed(dem_path, lat, lon)
    risk = calculate_flood_risk(
        elev["elevation_m"],
        watershed["catchment_area_km2"],
        watershed["flow_accumulation_at_site"]
    )

    return {
        "place": place_name,
        "coordinates": coords,
        "elevation": elev,
        "watershed": watershed,
        "risk": risk,
        "input_type": "city_name"
    }


def full_site_analysis_from_coords(lat: float, lon: float, radius_m: int = 1000):
    """Lat/Lon + radius based analysis."""
    print(f"Analysing flood risk for coordinates: {lat}, {lon}")

    # Build a circular buffer as bbox
    deg_offset = radius_m / 111000
    bbox = {
        "south": lat - deg_offset * 2,
        "north": lat + deg_offset * 2,
        "west": lon - deg_offset * 2,
        "east": lon + deg_offset * 2,
        "center_lat": lat,
        "center_lon": lon,
    }

    dem_path, _ = download_dem_for_bbox(bbox, f"site_{lat:.4f}_{lon:.4f}")
    elev = query_elevation(lat, lon, dem_path)
    watershed = analyze_watershed(dem_path, lat, lon)
    risk = calculate_flood_risk(
        elev["elevation_m"],
        watershed["catchment_area_km2"],
        watershed["flow_accumulation_at_site"]
    )

    return {
        "place": f"Site at {lat:.5f}, {lon:.5f}",
        "coordinates": {"lat": lat, "lon": lon, "display_name": f"{lat:.5f}°N, {lon:.5f}°E"},
        "elevation": elev,
        "watershed": watershed,
        "risk": risk,
        "input_type": "coordinates"
    }


def full_site_analysis_from_polygon(geojson: dict):
    """GeoJSON polygon based analysis with DEM clipping."""
    print("Analysing flood risk for uploaded polygon...")

    bbox = get_polygon_bbox(geojson)
    lat, lon = bbox["center_lat"], bbox["center_lon"]

    # Download DEM for polygon bbox
    dem_path, _ = download_dem_for_bbox(bbox, f"polygon_{lat:.4f}_{lon:.4f}")

    # Clip DEM to polygon
    clipped_path = f"data/dem/clipped_{lat:.4f}_{lon:.4f}.tif"
    clip_dem_to_polygon(dem_path, geojson, clipped_path)

    # Use clipped DEM for stats
    elev_stats = query_elevation_stats(clipped_path)
    watershed = analyze_watershed(clipped_path, lat, lon)
    risk = calculate_flood_risk(
        elev_stats["elevation_mean_m"],
        watershed["catchment_area_km2"],
        watershed["flow_accumulation_at_site"]
    )

    return {
        "place": "Uploaded site polygon",
        "coordinates": {"lat": lat, "lon": lon, "display_name": f"Custom polygon · centroid {lat:.4f}°N, {lon:.4f}°E"},
        "elevation": elev_stats,
        "watershed": watershed,
        "risk": risk,
        "input_type": "polygon",
        "polygon_geojson": geojson
    }