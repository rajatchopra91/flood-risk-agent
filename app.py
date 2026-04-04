import os
import json
import math
import requests
import gradio as gr
from tools import full_site_analysis
from groq import Groq
from dotenv import load_dotenv
from dem_downloader import precache_cities, RateLimitError
import plotly.graph_objects as go

load_dotenv()

SEASON_MULTIPLIERS = {
    "🌧️ Monsoon (Jun–Sep)": 1.6,
    "🌦️ Post-monsoon (Oct–Dec)": 1.2,
    "☀️ Dry Season (Jan–May)": 0.8
}

URISK_LOGO = "data:image/png;base64,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"

MAX_POLYGON_KM2 = 25.0

REJECTED_LOCATIONS = {
    "india", "bharat", "south asia", "asia", "unknown", "location",
    "city", "town", "village", "place", "area", "region", "state", "country",
}

CACHED_CITY_KEYS = {
    "mumbai", "delhi", "bangalore", "bengaluru", "hyderabad", "chennai",
    "kolkata", "pune", "ahmedabad", "jaipur", "lucknow", "surat", "bhopal",
    "patna", "nagpur", "indore", "noida", "bandra", "bhagalpur", "sirsa",
    "haridwar", "dehradun", "srinagar", "thane", "whitefield", "koregaon park",
    "koregaon_park",
}


def is_dem_cached(location: str) -> bool:
    key = location.lower().strip().replace(",", "").replace(" ", "_")
    first = key.split("_")[0]
    for candidate in [key, first]:
        if os.path.exists(f"data/dem/{candidate}_dem.tif"):
            return True
    loc_lower = location.lower()
    for city_key in CACHED_CITY_KEYS:
        if city_key in loc_lower:
            if os.path.exists(f"data/dem/{city_key.replace(' ', '_')}_dem.tif"):
                return True
    return False


def _rate_limit_msg() -> str:
    return (
        "⚠️ OpenTopography API daily limit reached (50 calls/24hrs). "
        "Pre-cached cities (Mumbai, Delhi, Bangalore, Pune etc.) still work instantly. "
        "New city downloads via Planetary Computer are unaffected."
    )


def polygon_area_km2(geojson: dict) -> float:
    try:
        if geojson.get("type") == "FeatureCollection":
            coords = geojson["features"][0]["geometry"]["coordinates"][0]
        elif geojson.get("type") == "Feature":
            coords = geojson["geometry"]["coordinates"][0]
        else:
            coords = geojson["coordinates"][0]
        n = len(coords)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            xi = coords[i][0] * math.pi / 180
            yi = coords[i][1] * math.pi / 180
            xj = coords[j][0] * math.pi / 180
            yj = coords[j][1] * math.pi / 180
            area += (xj - xi) * (2 + math.sin(yi) + math.sin(yj))
        return abs(area * 6371 * 6371 / 2)
    except Exception:
        return 0.0


def get_osm_boundary(place_name: str):
    """
    Get OSM boundary polygon for a place.
    Uses limit=5, picks first Polygon/MultiPolygon result.
    Falls through 4 strategies before giving up.
    """
    def _query(q, extra_params=None):
        params = {"q": f"{q}, India", "format": "json",
                  "limit": 5, "polygon_geojson": 1}
        if extra_params:
            params.update(extra_params)
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
                headers={"User-Agent": "flood-risk-agent"},
                timeout=10
            )
            return resp.json()
        except Exception:
            return []

    def _first_polygon(results):
        for r in results:
            geom = r.get("geojson", {})
            if geom.get("type") in ("Polygon", "MultiPolygon"):
                return json.dumps(geom)
        return None

    # Strategy 1: full name, pick first polygon from top 5
    polygon = _first_polygon(_query(place_name))
    if polygon:
        return polygon

    # Strategy 2: first part only e.g. "Koregaon Park" from "Koregaon Park, Pune"
    first_part = place_name.split(",")[0].strip()
    if first_part != place_name:
        polygon = _first_polygon(_query(first_part))
        if polygon:
            return polygon

    # Strategy 3: city-level admin boundary
    polygon = _first_polygon(_query(place_name, {"featuretype": "city"}))
    if polygon:
        return polygon

    # Strategy 4: district-level fallback (covers cities like Mysore/Mysuru
    # where city polygon isn't indexed but district boundary is)
    city_name = place_name.split(",")[0].strip()
    polygon = _first_polygon(_query(f"{city_name} District"))
    if polygon:
        return polygon

    return None  # marker still shows, just no boundary fill


def create_plotly_map(lat, lon, risk_level, place_name, elevation,
                      catchment, score, season, boundary_geojson=None,
                      polygon_geojson_str=None):
    risk_colors = {"High": "#c62828", "Moderate": "#e65100", "Low": "#2e7d32"}
    color = risk_colors.get(risk_level, "#1565c0")
    elev_str = f"{elevation:.1f}" if isinstance(elevation, float) else str(elevation)
    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)

    fig = go.Figure()

    if boundary_geojson:
        try:
            geom = json.loads(boundary_geojson)
            rings = []
            if geom["type"] == "Polygon":
                rings = [geom["coordinates"][0]]
            elif geom["type"] == "MultiPolygon":
                rings = [p[0] for p in geom["coordinates"]]
            for ring in rings:
                fig.add_trace(go.Scattermap(
                    lon=[c[0] for c in ring], lat=[c[1] for c in ring],
                    mode="lines", line=dict(color=color, width=2.5),
                    fill="toself", fillcolor=f"rgba({r},{g},{b},0.15)",
                    name="Admin boundary", showlegend=True, hoverinfo="skip",
                    legendgroup="boundary"
                ))
        except Exception:
            pass

    if polygon_geojson_str:
        try:
            geom = json.loads(polygon_geojson_str)
            coords = geom.get("coordinates", [[]])[0]
            fig.add_trace(go.Scattermap(
                lon=[c[0] for c in coords], lat=[c[1] for c in coords],
                mode="lines", line=dict(color="#1565c0", width=2.5),
                fill="toself", fillcolor="rgba(21,101,192,0.2)",
                name="Site boundary", showlegend=True, hoverinfo="skip"
            ))
        except Exception:
            pass

    fig.add_trace(go.Scattermap(
        lon=[lon], lat=[lat], mode="markers",
        marker=dict(size=14, color=color, symbol="circle"),
        customdata=[[place_name, elev_str, catchment, season, score]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            f"{risk_level} Risk — {score}/100<br>"
            "Elevation: %{customdata[1]}m<br>"
            "Catchment: %{customdata[2]} km²<br>"
            "Season: %{customdata[3]}<extra></extra>"
        ),
        name=place_name, showlegend=False
    ))

    fig.update_layout(
        map=dict(style="open-street-map", center=dict(lat=lat, lon=lon), zoom=11),
        margin=dict(l=0, r=0, t=0, b=0), height=450,
        paper_bgcolor="#f0f4f8",
        legend=dict(x=0.01, y=0.99, bgcolor="white", bordercolor=color,
                    borderwidth=1.5, font=dict(size=11)),
        annotations=[dict(
            x=0.01, y=0.97, xref="paper", yref="paper",
            xanchor="left", yanchor="top",
            text=(f"<b>{place_name}</b><br>"
                  f"<span style=\'color:{color}\'>{risk_level} Risk — {score}/100</span><br>"
                  f"Elevation: {elev_str}m<br>"
                  f"Catchment: {catchment} km²<br>"
                  f"{season}"),
            showarrow=False, bgcolor="white",
            bordercolor=color, borderwidth=2, borderpad=8,
            font=dict(size=11)
        )]
    )
    return fig


def extract_location(user_query: str) -> str:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    extraction = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": (
                "You are a location extractor. Output ONLY the place name — nothing else. "
                "Examples:\n"
                "Input: Is Bhagalpur safe for a data center? → Output: Bhagalpur\n"
                "Input: flood risk in Bandra Mumbai → Output: Bandra, Mumbai\n"
                "Input: Should I build in Whitefield Bangalore? → Output: Whitefield, Bangalore\n"
                "Input: hsr bengaluru good for warehouse → Output: HSR Layout, Bengaluru\n"
                "Never refuse. Always output just the place name."
            )},
            {"role": "user", "content": user_query}
        ], temperature=0.0
    )
    raw = extraction.choices[0].message.content.strip()
    return raw.split("\n")[0].strip().strip("'\"")


def generate_report(user_query: str, data: dict, season: str) -> str:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    clean_data = {
        "place": data.get("place"), "input_type": data.get("input_type"),
        "season": data.get("season"),
        "coordinates": data.get("coordinates", {}).get("display_name"),
        "elevation": {k: v for k, v in data.get("elevation", {}).items()
                      if k in ["elevation_m","elevation_mean_m","elevation_min_m","elevation_max_m"]},
        "watershed": {"catchment_area_km2": data.get("watershed",{}).get("catchment_area_km2"),
                      "flow_accumulation_at_site": data.get("watershed",{}).get("flow_accumulation_at_site")},
        "risk": data.get("risk")
    }
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": (
                "You are a flood risk analyst for Indian construction sites. "
                "Write a 3-4 sentence plain-language indicative assessment. "
                "IMPORTANT: Always use the exact risk_level and risk_score from the data. "
                "When mentioning season, clarify it is a modelled scenario, not measured data. "
                "End with: For a detailed certified assessment, consult a flood risk specialist at uRisk. "
                "Be specific with numbers. No bullet points."
            )},
            {"role": "user", "content": f"Query: {user_query}\nSeason: {season}\nData: {json.dumps(clean_data)}"}
        ]
    )
    return response.choices[0].message.content


def apply_season(data: dict, season: str):
    multiplier = SEASON_MULTIPLIERS.get(season, 1.0)
    adjusted_score = min(100, int(data["risk"]["risk_score"] * multiplier))
    adjusted_risk = "High" if adjusted_score >= 70 else "Moderate" if adjusted_score >= 40 else "Low"
    data["risk"]["risk_score"] = adjusted_score
    data["risk"]["risk_level"] = adjusted_risk
    data["season"] = season
    return data


def get_elevation_display(data: dict) -> float:
    elev = data.get("elevation", {})
    return elev.get("elevation_mean_m") or elev.get("elevation_m") or 0.0


def analyse_location(user_query: str, season: str, progress=gr.Progress()):
    if not user_query.strip():
        return "Please enter a question.", DEFAULT_MAP, "No location identified."
    try:
        progress(0.1, desc="🔍 Extracting location...")
        location = extract_location(user_query)

        if location.lower().strip() in REJECTED_LOCATIONS or len(location.strip()) < 3:
            return (
                "Could not identify a specific location. "
                "Please mention a city or area in India.",
                DEFAULT_MAP, "Location unclear."
            )

        cached = is_dem_cached(location)
        dem_desc = "⚡ Loading from local cache..." if cached else "🌐 Fetching from Planetary Computer..."
        progress(0.3, desc=dem_desc)

        data = full_site_analysis(location)

        if data is None:
            return (
                "Analysis failed — could not retrieve elevation data. Try a major nearby city.",
                DEFAULT_MAP, "Data retrieval failed."
            )

        progress(0.6, desc="🌊 Analysing watershed & flood risk...")
        data = apply_season(data, season)
        lat = data["coordinates"]["lat"]
        lon = data["coordinates"]["lon"]
        elevation = get_elevation_display(data)
        catchment = data["watershed"]["catchment_area_km2"]
        display_name = data["coordinates"]["display_name"]
        progress(0.8, desc="🤖 Generating AI report...")
        report = generate_report(user_query, data, season)
        progress(0.9, desc="🗺️ Rendering map...")
        boundary = get_osm_boundary(location)
        fig = create_plotly_map(lat, lon, data["risk"]["risk_level"], location,
                                elevation, catchment, data["risk"]["risk_score"],
                                season, boundary_geojson=boundary)
        progress(1.0, desc="✅ Done!")
        return report, fig, f"📍 {display_name}"

    except RateLimitError:
        return _rate_limit_msg(), DEFAULT_MAP, "API rate limit reached."
    except Exception as e:
        err = str(e)
        if "429" in err or "rate limit" in err.lower() or "50 API calls" in err:
            return _rate_limit_msg(), DEFAULT_MAP, "API rate limit reached."
        return f"Error: {err}", DEFAULT_MAP, "Error."


def analyse_from_polygon(geojson_file, season: str, progress=gr.Progress()):
    if geojson_file is None:
        return "Please upload a GeoJSON file.", DEFAULT_MAP, "No file uploaded."
    try:
        progress(0.1, desc="📂 Reading polygon...")
        file_size_kb = os.path.getsize(geojson_file.name) / 1024
        if file_size_kb > 500:
            return f"File too large ({file_size_kb:.0f}KB). Max 500KB.", DEFAULT_MAP, "File too large."
        with open(geojson_file.name, "r") as f:
            geojson = json.load(f)
        area = polygon_area_km2(geojson)
        if area > MAX_POLYGON_KM2:
            return (
                f"Polygon too large ({area:.1f} km²). Max {MAX_POLYGON_KM2} km².",
                DEFAULT_MAP, "Polygon too large."
            )
        progress(0.3, desc="🌐 Fetching DEM from Planetary Computer...")
        from tools import full_site_analysis_from_polygon
        data = full_site_analysis_from_polygon(geojson)

        if data is None:
            return (
                "Analysis failed — could not retrieve elevation data for this polygon.",
                DEFAULT_MAP, "Data retrieval failed."
            )

        progress(0.6, desc="🌊 Analysing flood risk...")
        data = apply_season(data, season)
        elevation = get_elevation_display(data)
        catchment = data["watershed"]["catchment_area_km2"]
        lat = data["coordinates"]["lat"]
        lon = data["coordinates"]["lon"]
        progress(0.8, desc="🤖 Generating report...")
        report = generate_report("Flood risk for uploaded polygon site", data, season)
        progress(0.9, desc="🗺️ Rendering map...")
        raw = data.get("polygon_geojson", {})
        if raw.get("type") == "FeatureCollection":
            poly = json.dumps(raw["features"][0]["geometry"])
        elif raw.get("type") == "Feature":
            poly = json.dumps(raw["geometry"])
        else:
            poly = json.dumps(raw)
        fig = create_plotly_map(lat, lon, data["risk"]["risk_level"], "Uploaded Site",
                                elevation, catchment, data["risk"]["risk_score"],
                                season, polygon_geojson_str=poly)
        progress(1.0, desc="✅ Done!")
        return report, fig, f"📍 {data['coordinates']['display_name']}"

    except RateLimitError:
        return _rate_limit_msg(), DEFAULT_MAP, "API rate limit reached."
    except Exception as e:
        err = str(e)
        if "429" in err or "rate limit" in err.lower() or "50 API calls" in err:
            return _rate_limit_msg(), DEFAULT_MAP, "API rate limit reached."
        return f"Error: {err}", DEFAULT_MAP, "Error in analysis."


def default_india_map() -> go.Figure:
    cities = [
        ("Mumbai", 19.076, 72.877), ("Delhi", 28.704, 77.102),
        ("Bangalore", 12.972, 77.594), ("Hyderabad", 17.385, 78.487),
        ("Chennai", 13.083, 80.270), ("Kolkata", 22.573, 88.364),
        ("Pune", 18.520, 73.856), ("Ahmedabad", 23.023, 72.572),
        ("Jaipur", 26.912, 75.787), ("Lucknow", 26.847, 80.947),
        ("Patna", 25.594, 85.137), ("Bhagalpur", 25.244, 86.972),
        ("Bhopal", 23.259, 77.413), ("Nagpur", 21.145, 79.088),
        ("Surat", 21.170, 72.831), ("Indore", 22.719, 75.857),
        ("Noida", 28.535, 77.391), ("Dehradun", 30.317, 78.032),
        ("Haridwar", 29.945, 78.164), ("Srinagar", 34.084, 74.797),
        ("Bandra", 19.054, 72.840), ("Whitefield", 12.969, 77.750),
        ("Koregaon Park", 18.537, 73.893), ("Thane", 19.218, 72.978),
        ("Sirsa", 29.533, 75.029),
    ]
    fig = go.Figure()
    fig.add_trace(go.Scattermap(
        lat=[c[1] for c in cities], lon=[c[2] for c in cities],
        mode="markers+text",
        marker=dict(size=8, color="#1565c0", opacity=0.7),
        text=[c[0] for c in cities], textposition="top right",
        textfont=dict(size=10, color="#1565c0"),
        hovertemplate="<b>%{text}</b><br>Pre-cached — instant analysis<extra></extra>",
        name="Pre-cached cities", showlegend=False
    ))
    fig.update_layout(
        map=dict(style="open-street-map", center=dict(lat=22.5, lon=82.0), zoom=4),
        margin=dict(l=0, r=0, t=0, b=0), height=450,
        paper_bgcolor="#f0f4f8",
        annotations=[dict(
            x=0.01, y=0.99, xref="paper", yref="paper",
            xanchor="left", yanchor="top",
            text="<b>25 pre-cached cities</b><br>Type a query and click Analyse Site",
            showarrow=False, bgcolor="white",
            bordercolor="#1565c0", borderwidth=1.5,
            borderpad=8, font=dict(size=11)
        )]
    )
    return fig


DEFAULT_MAP = default_india_map()

EXAMPLES_HTML = (
    "<div style=\'margin-top:12px;\'>"
    "<p style=\'font-size:12px;font-weight:600;margin-bottom:8px;font-family:sans-serif;color:#444;\'>💡 Try these examples</p>"
    "<div style=\'display:grid;grid-template-columns:1fr 1fr;gap:8px;\'>"
    "<button onclick=\'var t=document.querySelectorAll(\"textarea\")[0];t.value=\"Is Koregaon Park in Pune safe for a residential complex?\";t.dispatchEvent(new InputEvent(\"input\",{bubbles:true}));t.dispatchEvent(new Event(\"change\",{bubbles:true}));\'  style=\'background:#f0f7ff;border:2px solid #1565c0;border-radius:8px;padding:10px 12px;cursor:pointer;font-size:12px;font-family:sans-serif;text-align:left;width:100%;\'>  <div style=\'font-weight:700;color:#1565c0;margin-bottom:3px;\'>🏘️ Koregaon Park, Pune</div><div style=\'color:#555;\'>Residential complex · Monsoon</div></button>"
    "<button onclick=\'var t=document.querySelectorAll(\"textarea\")[0];t.value=\"Flood risk for construction in Bandra, Mumbai?\";t.dispatchEvent(new InputEvent(\"input\",{bubbles:true}));t.dispatchEvent(new Event(\"change\",{bubbles:true}));\'  style=\'background:#f0f7ff;border:2px solid #1565c0;border-radius:8px;padding:10px 12px;cursor:pointer;font-size:12px;font-family:sans-serif;text-align:left;width:100%;\'>  <div style=\'font-weight:700;color:#1565c0;margin-bottom:3px;\'>🌊 Bandra, Mumbai</div><div style=\'color:#555;\'>Construction site · Monsoon</div></button>"
    "<button onclick=\'var t=document.querySelectorAll(\"textarea\")[0];t.value=\"Should I build a warehouse in Whitefield, Bangalore?\";t.dispatchEvent(new InputEvent(\"input\",{bubbles:true}));t.dispatchEvent(new Event(\"change\",{bubbles:true}));\'  style=\'background:#f0f7ff;border:2px solid #1565c0;border-radius:8px;padding:10px 12px;cursor:pointer;font-size:12px;font-family:sans-serif;text-align:left;width:100%;\'>  <div style=\'font-weight:700;color:#1565c0;margin-bottom:3px;\'>🏭 Whitefield, Bangalore</div><div style=\'color:#555;\'>Warehouse · Dry Season</div></button>"
    "<button onclick=\'var t=document.querySelectorAll(\"textarea\")[0];t.value=\"Is Bhagalpur safe for a data center?\";t.dispatchEvent(new InputEvent(\"input\",{bubbles:true}));t.dispatchEvent(new Event(\"change\",{bubbles:true}));\'  style=\'background:#f0f7ff;border:2px solid #1565c0;border-radius:8px;padding:10px 12px;cursor:pointer;font-size:12px;font-family:sans-serif;text-align:left;width:100%;\'>  <div style=\'font-weight:700;color:#1565c0;margin-bottom:3px;\'>🖥️ Bhagalpur, Bihar</div><div style=\'color:#555;\'>Data center · Post-monsoon</div></button>"
    "</div></div>"
)

CSS = ".gradio-container { background: #f0f4f8 !important; font-family: \'Segoe UI\', sans-serif !important; } footer { display: none !important; }"
SEASON_INFO = "Adjusts risk score based on typical Indian rainfall patterns. Monsoon = worst case. Modelled estimate, not measured data."

DISCLAIMER = (
    "<div style=\'margin-top:12px;font-family:sans-serif;\'>"
    "<div style=\'background:#fff8e1;border:1.5px solid #f9a825;border-radius:8px;padding:10px 14px;margin-bottom:10px;\'>"
    "<p style=\'font-size:11px;color:#555;margin:0;line-height:1.6;\'>⚠️ <strong style=\'color:#333;\'>Indicative assessment only.</strong> "
    "Results are based on 30m DEM and modelled seasonal scenarios — not measured rainfall or hydrodynamic simulation. "
    "For detailed site-specific analysis, consult a specialist at uRISK.</p></div>"
    "<div style=\'background:white;border:2px solid #0d47a1;border-radius:10px;padding:12px 16px;display:flex;align-items:center;gap:14px;\'>"
    f"<img src=\'{URISK_LOGO}\' style=\'height:40px;object-fit:contain;flex-shrink:0;\' alt=\'uRisk\'/>"
    "<div><p style=\'margin:0;font-size:13px;font-weight:700;color:#0d47a1;\'>Need a detailed analysis?</p>"
    "<p style=\'margin:3px 0 0;font-size:12px;color:#555;\'>uRisk Consulting — geospatial flood risk assessments.</p>"
    "<a href=\'https://www.linkedin.com/company/urisk-consulting/\' target=\'_blank\' "
    "style=\'font-size:12px;color:#1565c0;font-weight:600;text-decoration:none;\'>→ Contact uRisk on LinkedIn</a>"
    "</div></div></div>"
)

HEADER = (
    "<div style=\'background:linear-gradient(135deg,#1565c0,#0d47a1);padding:16px 24px;border-radius:12px;margin-bottom:12px;"
    "display:flex;justify-content:space-between;align-items:center;\'>"
    "<div><h1 style=\'color:white;margin:0;font-size:22px;font-weight:700;\'>🌊 Flood Risk Agent — Analyze any site for Risk Score</h1>"
    "<p style=\'color:#bbdefb;margin:4px 0 0;font-size:13px;\'>Powered by Llama 3 &nbsp;·&nbsp; Copernicus DEM (30m) &nbsp;·&nbsp; OpenStreetMap</p></div>"
    f"<div style=\'background:white;padding:8px 14px;border-radius:10px;\'>"
    f"<img src=\'{URISK_LOGO}\' style=\'height:48px;object-fit:contain;\' alt=\'uRisk\'/></div></div>"
)

with gr.Blocks(title="Flood Risk Agent") as app:

    gr.HTML(HEADER)
    with gr.Tabs():

        with gr.Tab("Search by City"):
            with gr.Row(equal_height=True):
                with gr.Column(scale=1, min_width=320):
                    query_input = gr.Textbox(label="Your Question",
                        placeholder="e.g. Is HSR Layout in Bangalore safe for a warehouse?", lines=2)
                    season_input = gr.Radio(choices=list(SEASON_MULTIPLIERS.keys()),
                        value="🌧️ Monsoon (Jun–Sep)", label="🗓️ Seasonal Risk Scenario", info=SEASON_INFO)
                    submit_btn = gr.Button("🔍 Analyse Site", variant="primary")
                    location_info = gr.Textbox(label="📍 Location Identified", interactive=False, lines=1)
                    report_output = gr.Textbox(label="🤖 AI Flood Risk Report", lines=5, interactive=False)
                with gr.Column(scale=2, min_width=500):
                    map_output = gr.Plot(value=DEFAULT_MAP, show_label=False)
                    gr.HTML(EXAMPLES_HTML)
                    gr.HTML(DISCLAIMER)
            submit_btn.click(fn=analyse_location, inputs=[query_input, season_input],
                             outputs=[report_output, map_output, location_info], api_name=False)

        with gr.Tab("Upload Site Polygon"):
            gr.HTML("<p style=\'font-family:sans-serif;font-size:13px;color:#555;margin:8px 0;\'>Upload a GeoJSON file of your site boundary (max 25 km², max 500KB).</p>")
            with gr.Row(equal_height=True):
                with gr.Column(scale=1, min_width=320):
                    geojson_input = gr.File(label="Upload GeoJSON (.geojson or .json)", file_types=[".geojson", ".json"])
                    season_input_3 = gr.Radio(choices=list(SEASON_MULTIPLIERS.keys()),
                        value="🌧️ Monsoon (Jun–Sep)", label="🗓️ Seasonal Risk Scenario", info=SEASON_INFO)
                    submit_btn_3 = gr.Button("🔍 Analyse Polygon", variant="primary")
                    location_info_3 = gr.Textbox(label="📍 Site Info", interactive=False, lines=1)
                    report_output_3 = gr.Textbox(label="🤖 AI Flood Risk Report", lines=5, interactive=False)
                with gr.Column(scale=2, min_width=500):
                    map_output_3 = gr.Plot(value=DEFAULT_MAP, show_label=False)
                    gr.HTML(EXAMPLES_HTML)
                    gr.HTML(DISCLAIMER)
            submit_btn_3.click(fn=analyse_from_polygon, inputs=[geojson_input, season_input_3],
                               outputs=[report_output_3, map_output_3, location_info_3], api_name=False)

if __name__ == "__main__":
    app.launch(theme=gr.themes.Soft(), css=CSS)
