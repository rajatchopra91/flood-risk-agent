import os
import gc
import json
import warnings
import numpy as np
import rasterio
from rasterio.transform import rowcol
from rasterio.mask import mask as rio_mask
from shapely.geometry import shape
from pysheds.grid import Grid
from geopy.geocoders import Nominatim
from dem_downloader import download_dem, download_dem_for_bbox, RateLimitError

warnings.filterwarnings("ignore", category=UserWarning, module="pysheds")


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
    # Round to 2dp for cache key consistency (~1km precision)
    lat = round((bounds[1] + bounds[3]) / 2, 2)
    lon = round((bounds[0] + bounds[2]) / 2, 2)
    padding = 0.05
    return {
        "south": bounds[1] - padding,
        "north": bounds[3] + padding,
        "west": bounds[0] - padding,
        "east": bounds[2] + padding,
        "center_lat": lat,
        "center_lon": lon,
    }


def get_polygon_centroid(geojson: dict):
    geom = shape(get_polygon_geometry(geojson))
    centroid = geom.centroid
    return centroid.y, centroid.x


def clip_dem_to_polygon(dem_path: str, geojson: dict, output_path: str):
    """Clip DEM to polygon boundary."""
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
        data = src.read(1)
        nodata = src.nodata if src.nodata is not None else -9999
        elev = float(data[row, col])
        # Fallback to mean if nodata hit
        if elev == nodata or elev < -500:
            valid = data[data != nodata]
            elev = float(valid.mean()) if valid.size > 0 else 0.0
    return {"elevation_m": elev, "lat": lat, "lon": lon}


def query_elevation_stats(dem_path: str):
    """Get min/max/mean elevation from a clipped DEM."""
    with rasterio.open(dem_path) as src:
        data = src.read(1)
        nodata = src.nodata if src.nodata is not None else -9999
        valid = data[data != nodata]
        if valid.size == 0:
            return {"elevation_min_m": 0.0, "elevation_max_m": 0.0,
                    "elevation_mean_m": 0.0, "elevation_m": 0.0}
    return {
        "elevation_min_m": float(valid.min()),
        "elevation_max_m": float(valid.max()),
        "elevation_mean_m": float(valid.mean()),
        "elevation_m": float(valid.mean())
    }


def analyze_watershed(dem_path: str, lat: float, lon: float):
    grid = None
    try:
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
        flow_at_site = float(acc[grid.nearest_cell(x, y)])

        return {
            "catchment_area_km2": round(catchment_area_km2, 2),
            "snap_lat": snap_y,
            "snap_lon": snap_x,
            "flow_accumulation_at_site": flow_at_site
        }
    finally:
        # Explicit cleanup to free DEM arrays from memory
        del grid
        gc.collect()


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


def cleanup_old_clipped_dems(output_dir: str = "data/dem", max_files: int = 10):
    """Remove oldest clipped_*.tif files — prevents disk bloat on HF Spaces."""
    try:
        clipped = [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.startswith("clipped_") and f.endswith(".tif")
        ]
        if len(clipped) > max_files:
            clipped.sort(key=os.path.getmtime)
            for f in clipped[:len(clipped) - max_files]:
                os.remove(f)
                print(f"Cleaned up old clipped DEM: {f}")
    except Exception as e:
        print(f"DEM cleanup warning: {e}")


def full_site_analysis(place_name: str):
    """City name based analysis."""
    print(f"Analysing flood risk for: {place_name}")
    try:
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
    except RateLimitError:
        raise  # Let app.py handle with specific message
    except Exception as e:
        print(f"full_site_analysis error for {place_name}: {e}")
        return None  # app.py None guard catches this


def full_site_analysis_from_coords(lat: float, lon: float, radius_m: int = 1000):
    """Lat/Lon + radius based analysis."""
    print(f"Analysing flood risk for coordinates: {lat}, {lon}")
    try:
        deg_offset = radius_m / 111000
        bbox = {
            "south": lat - deg_offset * 2,
            "north": lat + deg_offset * 2,
            "west": lon - deg_offset * 2,
            "east": lon + deg_offset * 2,
            "center_lat": round(lat, 2),
            "center_lon": round(lon, 2),
        }
        dem_path, _ = download_dem_for_bbox(bbox, f"site_{round(lat,2)}_{round(lon,2)}")
        elev = query_elevation(lat, lon, dem_path)
        watershed = analyze_watershed(dem_path, lat, lon)
        risk = calculate_flood_risk(
            elev["elevation_m"],
            watershed["catchment_area_km2"],
            watershed["flow_accumulation_at_site"]
        )
        return {
            "place": f"Site at {lat:.5f}, {lon:.5f}",
            "coordinates": {"lat": lat, "lon": lon,
                            "display_name": f"{lat:.5f}°N, {lon:.5f}°E"},
            "elevation": elev,
            "watershed": watershed,
            "risk": risk,
            "input_type": "coordinates"
        }
    except RateLimitError:
        raise
    except Exception as e:
        print(f"full_site_analysis_from_coords error: {e}")
        return None


def full_site_analysis_from_polygon(geojson: dict):
    """GeoJSON polygon based analysis with DEM clipping."""
    print("Analysing flood risk for uploaded polygon...")
    try:
        bbox = get_polygon_bbox(geojson)
        lat, lon = bbox["center_lat"], bbox["center_lon"]

        # 2dp rounded key for cache consistency
        dem_path, _ = download_dem_for_bbox(bbox, f"polygon_{lat}_{lon}")

        # Clip DEM to polygon boundary
        clipped_path = f"data/dem/clipped_{lat}_{lon}.tif"
        clip_dem_to_polygon(dem_path, geojson, clipped_path)

        elev_stats = query_elevation_stats(clipped_path)
        watershed = analyze_watershed(clipped_path, lat, lon)
        risk = calculate_flood_risk(
            elev_stats["elevation_mean_m"],
            watershed["catchment_area_km2"],
            watershed["flow_accumulation_at_site"]
        )

        # Cleanup old clipped files to save disk
        cleanup_old_clipped_dems()

        return {
            "place": "Uploaded site polygon",
            "coordinates": {
                "lat": lat, "lon": lon,
                "display_name": f"Custom polygon · centroid {lat:.4f}°N, {lon:.4f}°E"
            },
            "elevation": elev_stats,
            "watershed": watershed,
            "risk": risk,
            "input_type": "polygon",
            "polygon_geojson": geojson
        }
    except RateLimitError:
        raise
    except Exception as e:
        print(f"full_site_analysis_from_polygon error: {e}")
        return None
