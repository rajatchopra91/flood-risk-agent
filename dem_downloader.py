import os
import requests
import numpy as np
from dotenv import load_dotenv
from geocoder import geocode_bbox

load_dotenv()

OPENTOPO_KEY = os.getenv("OPENTOPO_API_KEY")
PC_COLLECTION = "cop-dem-glo-30"  # Copernicus 30m — best India coverage, no rate limit

TOP_CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
    "Pune", "Kolkata", "Ahmedabad", "Jaipur", "Lucknow",
    "Surat", "Bhopal", "Patna", "Nagpur", "Indore"
]

# Pre-cached cities protected from eviction
PROTECTED_DEMS = {f"{c.lower().replace(' ', '_')}_dem.tif" for c in [
    "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata",
    "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Surat", "Bhopal", "Patna",
    "Nagpur", "Indore", "Noida", "Bandra", "Bhagalpur", "Sirsa", "Haridwar",
    "Dehradun", "Srinagar", "Thane", "Whitefield", "Koregaon Park"
]}


class RateLimitError(Exception):
    """Raised when OpenTopography API 429 rate limit is hit."""
    pass


def cleanup_dem_cache(output_dir: str = "data/dem", max_mb: int = 400):
    """
    Size-based cache eviction — removes oldest non-protected DEMs
    when total cache exceeds max_mb. Protects pre-cached city files.
    """
    try:
        files = [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.endswith(".tif")
        ]
        total_mb = sum(os.path.getsize(f) for f in files) / (1024 * 1024)
        if total_mb <= max_mb:
            return
        print(f"DEM cache at {total_mb:.0f}MB — evicting oldest files...")
        evictable = sorted(
            [f for f in files if os.path.basename(f) not in PROTECTED_DEMS],
            key=os.path.getmtime
        )
        for f in evictable:
            if total_mb <= max_mb:
                break
            size_mb = os.path.getsize(f) / (1024 * 1024)
            os.remove(f)
            total_mb -= size_mb
            print(f"  Evicted: {os.path.basename(f)} ({size_mb:.1f}MB)")
    except Exception as e:
        print(f"Cache cleanup warning: {e}")


def download_dem_stac(bbox: dict, output_path: str) -> str:
    """
    Download DEM from Microsoft Planetary Computer (STAC).
    Uses Copernicus GLO-30 (30m) — no rate limit, streams only needed pixels.
    """
    import pystac_client
    import planetary_computer
    import stackstac
    import rasterio
    from rasterio.transform import from_bounds

    south, north = bbox["south"], bbox["north"]
    west, east = bbox["west"], bbox["east"]

    print(f"Fetching DEM from Planetary Computer (STAC)...")
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace
    )

    search = catalog.search(
        collections=[PC_COLLECTION],
        bbox=[west, south, east, north]
    )
    items = list(search.items())
    if not items:
        raise ValueError(f"No STAC tiles found for bbox")

    print(f"  Found {len(items)} STAC tile(s)")

    # epsg=4326 required — Copernicus tiles don't embed CRS in metadata
    stack = stackstac.stack(
        items,
        assets=["data"],
        epsg=4326,
        bounds_latlon=[west, south, east, north],
        resolution=0.0002777  # ~30m in degrees
    )

    # mean() merges overlapping tiles cleanly, squeeze to 2D
    arr = stack.mean(dim="time").squeeze().compute()
    if arr.ndim != 2:
        arr = arr[0]

    data = arr.values.astype(np.float32)
    height, width = data.shape
    transform = from_bounds(west, south, east, north, width, height)

    os.makedirs(os.path.dirname(output_path) or "data/dem", exist_ok=True)
    tmp_path = output_path + ".tmp"
    try:
        with rasterio.open(
            tmp_path, "w",
            driver="GTiff",
            height=height, width=width,
            count=1, dtype="float32",
            crs="EPSG:4326",
            transform=transform,
            nodata=-9999
        ) as dst:
            dst.write(data, 1)
        os.replace(tmp_path, output_path)
        print(f"DEM saved via STAC: {output_path}")
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise Exception(f"Write failed: {e}")

    return output_path


def _download_opentopo(bbox: dict, output_path: str) -> str:
    """OpenTopography fallback — atomic write + rate limit detection."""
    params = {
        "demtype": "AW3D30",
        "south": bbox["south"], "north": bbox["north"],
        "west": bbox["west"], "east": bbox["east"],
        "outputFormat": "GTiff", "API_Key": OPENTOPO_KEY
    }
    response = requests.get(
        "https://portal.opentopography.org/API/globaldem",
        params=params, stream=True, timeout=60
    )
    if response.status_code == 429:
        reset = response.headers.get("X-RateLimit-Reset", "")
        msg = "OpenTopography rate limit hit (50 calls/24hrs)."
        if reset:
            msg += f" Resets at: {reset} UTC."
        raise RateLimitError(msg)
    if response.status_code != 200:
        raise Exception(f"OpenTopography failed: {response.status_code} - {response.text}")

    tmp_path = output_path + ".tmp"
    try:
        with open(tmp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        os.replace(tmp_path, output_path)
        print(f"DEM saved via OpenTopography: {output_path}")
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise Exception(f"Write failed: {e}")
    return output_path


def _download_with_fallback(bbox: dict, output_path: str) -> str:
    """STAC primary -> OpenTopography fallback -> RateLimitError."""
    try:
        return download_dem_stac(bbox, output_path)
    except Exception as e:
        print(f"STAC failed, falling back to OpenTopography: {e}")
    return _download_opentopo(bbox, output_path)


def download_dem(city_name: str, output_dir: str = "data/dem"):
    """Download DEM for a city. STAC primary, OpenTopography fallback."""
    os.makedirs(output_dir, exist_ok=True)
    bbox = geocode_bbox(city_name, offset=0.10)
    output_path = f"{output_dir}/{city_name.lower().replace(' ', '_')}_dem.tif"

    if os.path.exists(output_path):
        print(f"Cache hit: {output_path}")
        return output_path, bbox

    print(f"Downloading DEM for {city_name} (via {bbox.get('geocoder', 'unknown')})...")
    _download_with_fallback(bbox, output_path)
    cleanup_dem_cache(output_dir)
    return output_path, bbox


def download_dem_for_bbox(bbox: dict, name: str, output_dir: str = "data/dem"):
    """Download DEM for explicit bbox (polygon/coords). STAC primary, fallback OpenTopography."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = f"{output_dir}/{name.replace(' ', '_')}_dem.tif"

    if os.path.exists(output_path):
        print(f"Cache hit: {output_path}")
        return output_path, bbox

    print(f"Downloading DEM for bbox: {name}...")
    _download_with_fallback(bbox, output_path)
    cleanup_dem_cache(output_dir)
    return output_path, bbox


def precache_cities():
    """Pre-download DEMs for top Indian cities in background threads."""
    import threading

    def cache_one(city):
        try:
            download_dem(city)
        except RateLimitError as e:
            print(f"Pre-cache rate limited: {e}")
        except Exception as e:
            print(f"Pre-cache skipped {city}: {e}")

    print(f"Pre-caching DEMs for {len(TOP_CITIES)} cities...")
    for city in TOP_CITIES:
        t = threading.Thread(target=cache_one, args=(city,), daemon=True)
        t.start()
    print("Pre-caching running in background — app ready!")


if __name__ == "__main__":
    path, bbox = download_dem("Varanasi")
    print(f"Success: {path}, geocoder: {bbox.get('geocoder')}")
