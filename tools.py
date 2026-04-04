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
from geocoder import geocode
from dem_downloader import download_dem, download_dem_for_bbox, RateLimitError, cleanup_dem_cache

warnings.filterwarnings("ignore", category=UserWarning, module="pysheds")


def get_polygon_geometry(geojson: dict):
    if geojson.get("type") == "Polygon":
        return geojson
    elif geojson.get("type") == "Feature":
        return geojson["geometry"]
    elif geojson.get("type") == "FeatureCollection":
        return geojson["features"][0]["geometry"]
    raise ValueError(f"Unsupported GeoJSON type: {geojson.get('type')}")


def get_polygon_bbox(geojson: dict):
    geom = shape(get_polygon_geometry(geojson))
    bounds = geom.bounds
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


def clip_dem_to_polygon(dem_path: str, geojson: dict, output_path: str):
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


def get_coordinates(place_name: str) -> dict:
    """Geocode via Photon -> Nominatim fallback."""
    result = geocode(place_name)
    return {
        "lat": result["lat"],
        "lon": result["lon"],
        "display_name": result["display_name"]
    }


def query_elevation(lat: float, lon: float, dem_path: str):
    with rasterio.open(dem_path) as src:
        row, col = rowcol(src.transform, lon, lat)
        data = src.read(1)
        nodata = src.nodata if src.nodata is not None else -9999
        elev = float(data[row, col])
        if elev == nodata or elev < -500:
            valid = data[data != nodata]
            elev = float(valid.mean()) if valid.size > 0 else 0.0
    return {"elevation_m": elev, "lat": lat, "lon": lon}


def query_elevation_stats(dem_path: str):
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
        del grid
        gc.collect()


def calculate_flood_risk(elevation_m: float, catchment_area_km2: float, flow_accumulation: float):
    elev_score = 40 if elevation_m < 10 else 30 if elevation_m < 50 else 15 if elevation_m < 100 else 5
    catch_score = 35 if catchment_area_km2 > 500 else 25 if catchment_area_km2 > 100 else 15 if catchment_area_km2 > 10 else 5
    flow_score = 25 if flow_accumulation > 10000 else 15 if flow_accumulation > 1000 else 5
    total = elev_score + catch_score + flow_score
    return {
        "risk_score": total,
        "risk_level": "High" if total >= 70 else "Moderate" if total >= 40 else "Low",
        "elevation_contribution": elev_score,
        "catchment_contribution": catch_score,
        "flow_contribution": flow_score
    }


def full_site_analysis(place_name: str):
    print(f"Analysing flood risk for: {place_name}")
    try:
        # Single geocode call — reuse coords for both DEM bbox and elevation query
        coords = get_coordinates(place_name)
        lat, lon = coords["lat"], coords["lon"]
        city = place_name.split(",")[0].strip()

        # Build bbox from already-geocoded coords (skip second geocode in download_dem)
        from dem_downloader import _download_with_fallback, cleanup_dem_cache, PROTECTED_DEMS
        import os
        output_dir = "data/dem"
        output_path = f"{output_dir}/{city.lower().replace(' ', '_')}_dem.tif"
        os.makedirs(output_dir, exist_ok=True)

        if os.path.exists(output_path):
            print(f"Cache hit: {output_path}")
            dem_path = output_path
        else:
            offset = 0.10
            bbox = {
                "south": lat - offset, "north": lat + offset,
                "west": lon - offset, "east": lon + offset,
                "center_lat": lat, "center_lon": lon
            }
            print(f"Downloading DEM for {city} (coords from Photon)...")
            _download_with_fallback(bbox, output_path)
            cleanup_dem_cache(output_dir)
            dem_path = output_path

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
        raise
    except Exception as e:
        print(f"full_site_analysis error for {place_name}: {e}")
        return None


def full_site_analysis_from_coords(lat: float, lon: float, radius_m: int = 1000):
    print(f"Analysing flood risk for coordinates: {lat}, {lon}")
    try:
        deg_offset = radius_m / 111000
        bbox = {
            "south": lat - deg_offset * 2, "north": lat + deg_offset * 2,
            "west": lon - deg_offset * 2, "east": lon + deg_offset * 2,
            "center_lat": round(lat, 2), "center_lon": round(lon, 2),
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
            "elevation": elev, "watershed": watershed,
            "risk": risk, "input_type": "coordinates"
        }
    except RateLimitError:
        raise
    except Exception as e:
        print(f"full_site_analysis_from_coords error: {e}")
        return None


def full_site_analysis_from_polygon(geojson: dict):
    print("Analysing flood risk for uploaded polygon...")
    try:
        bbox = get_polygon_bbox(geojson)
        lat, lon = bbox["center_lat"], bbox["center_lon"]
        dem_path, _ = download_dem_for_bbox(bbox, f"polygon_{lat}_{lon}")
        clipped_path = f"data/dem/clipped_{lat}_{lon}.tif"
        clip_dem_to_polygon(dem_path, geojson, clipped_path)
        elev_stats = query_elevation_stats(clipped_path)
        watershed = analyze_watershed(clipped_path, lat, lon)
        risk = calculate_flood_risk(
            elev_stats["elevation_mean_m"],
            watershed["catchment_area_km2"],
            watershed["flow_accumulation_at_site"]
        )
        cleanup_dem_cache()
        return {
            "place": "Uploaded site polygon",
            "coordinates": {
                "lat": lat, "lon": lon,
                "display_name": f"Custom polygon · centroid {lat:.4f}°N, {lon:.4f}°E"
            },
            "elevation": elev_stats, "watershed": watershed,
            "risk": risk, "input_type": "polygon",
            "polygon_geojson": geojson
        }
    except RateLimitError:
        raise
    except Exception as e:
        print(f"full_site_analysis_from_polygon error: {e}")
        return None
