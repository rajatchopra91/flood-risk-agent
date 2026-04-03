import os
import requests
from geopy.geocoders import Nominatim
from dotenv import load_dotenv

load_dotenv()

OPENTOPO_KEY = os.getenv("OPENTOPO_API_KEY")

# Top Indian cities to pre-cache on startup
TOP_CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
    "Pune", "Kolkata", "Ahmedabad", "Jaipur", "Lucknow",
    "Surat", "Bhopal", "Patna", "Nagpur", "Indore"
]


def get_city_bbox(city_name: str, country: str = "India"):
    geolocator = Nominatim(user_agent="flood-risk-agent")
    location = geolocator.geocode(f"{city_name}, {country}")

    if not location:
        raise ValueError(f"Could not find city: {city_name}")

    lat, lon = location.latitude, location.longitude
    offset = 0.10  # ~11km radius — was 0.15 (~17km), cuts download 55%
    return {
        "south": lat - offset,
        "north": lat + offset,
        "west": lon - offset,
        "east": lon + offset,
        "center_lat": lat,
        "center_lon": lon,
        "city": city_name
    }


def download_dem(city_name: str, output_dir: str = "data/dem"):
    os.makedirs(output_dir, exist_ok=True)

    bbox = get_city_bbox(city_name)

    output_path = f"{output_dir}/{city_name.lower().replace(' ', '_')}_dem.tif"

    if os.path.exists(output_path):
        return output_path, bbox

    print(f"Downloading DEM for {city_name}...")
    url = "https://portal.opentopography.org/API/globaldem"
    params = {
        "demtype": "AW3D30",
        "south": bbox["south"],
        "north": bbox["north"],
        "west": bbox["west"],
        "east": bbox["east"],
        "outputFormat": "GTiff",
        "API_Key": OPENTOPO_KEY
    }

    response = requests.get(url, params=params, stream=True, timeout=60)

    if response.status_code == 200:
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"DEM saved: {output_path}")
        return output_path, bbox
    else:
        raise Exception(f"Download failed: {response.status_code} - {response.text}")
def download_dem_for_bbox(bbox: dict, name: str, output_dir: str = "data/dem"):
    """Download DEM for an explicit bounding box."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = f"{output_dir}/{name.replace(' ', '_')}_dem.tif"

    if os.path.exists(output_path):
        return output_path, bbox

    print(f"Downloading DEM for bbox: {name}...")
    url = "https://portal.opentopography.org/API/globaldem"
    params = {
        "demtype": "AW3D30",
        "south": bbox["south"],
        "north": bbox["north"],
        "west": bbox["west"],
        "east": bbox["east"],
        "outputFormat": "GTiff",
        "API_Key": OPENTOPO_KEY
    }

    response = requests.get(url, params=params, stream=True, timeout=60)
    if response.status_code == 200:
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"DEM saved: {output_path}")
        return output_path, bbox
    else:
        raise Exception(f"Download failed: {response.status_code} - {response.text}")

def precache_cities():
    """Pre-download DEMs for top Indian cities in background threads."""
    import threading

    def cache_one(city):
        try:
            download_dem(city)
        except Exception as e:
            print(f"Pre-cache skipped {city}: {e}")

    print(f"Pre-caching DEMs for {len(TOP_CITIES)} cities in background...")
    threads = []
    for city in TOP_CITIES:
        t = threading.Thread(target=cache_one, args=(city,), daemon=True)
        t.start()
        threads.append(t)
    # Don't join — let them run in background
    print("Pre-caching running in background — app ready!")


if __name__ == "__main__":
    path, bbox = download_dem("Pune")
    print(f"Success: {path}")