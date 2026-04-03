---
title: Flood Risk Agent
emoji: 🌊
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: "6.10.0"
python_version: "3.11"
app_file: app.py
pinned: false
---

# 🌊 Flood Risk Agent — Indian Construction Sites

> AI-powered indicative flood risk assessment for construction site evaluation across India.
> Built with open-source geospatial data and LLM reasoning.

**Live Demo:** [huggingface.co/spaces/rajatchopra91/flood-risk-agent](https://huggingface.co/spaces/rajatchopra91/flood-risk-agent)

---

## What It Does

Site developers and construction planners can ask natural language questions about any location in India and receive:

- A **flood risk score** (0–100) with Low / Moderate / High classification
- **Elevation analysis** from 30m resolution satellite DEM data
- **Watershed & drainage analysis** — catchment area and flow accumulation
- **Seasonal risk adjustment** — Monsoon, Post-monsoon, or Dry Season scenarios
- An **interactive OSM map** with administrative boundary overlay
- An **AI-generated plain-language report** with construction recommendations

---

## Architecture

```
User Query (Natural Language)
        │
        ▼
┌─────────────────────┐
│   Gradio Frontend   │  ← HuggingFace Spaces (Python 3.11)
│   3 Input Modes:    │
│   • City Name       │
│   • Lat/Lon + Radius│
│   • GeoJSON Upload  │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Llama 3.1 8B       │  ← Groq API (location extraction)
│  Location Extractor │
└────────┬────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│           Geospatial Tool Pipeline          │
│                                             │
│  1. Geocoder        → Nominatim (OSM)       │
│  2. DEM Download    → OpenTopography API    │
│                       ALOS AW3D30 (30m)     │
│  3. DEM Clipping    → rasterio (polygon)    │
│  4. Watershed       → pysheds               │
│     • Pit filling                           │
│     • Flow direction (D8)                   │
│     • Flow accumulation                     │
│     • Catchment delineation                 │
│  5. Risk Scoring    → Custom algorithm      │
│     • Elevation contribution                │
│     • Catchment area contribution           │
│     • Flow accumulation contribution        │
│  6. Season Adjust   → Multiplier (0.8–1.6)  │
└────────┬────────────────────────────────────┘
         │
         ▼
┌─────────────────────┐
│  Llama 3.1 8B       │  ← Groq API (report generation)
│  Report Generator   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│              Output                         │
│  • AI Report (plain language)               │
│  • Plotly map (OSM + boundary + marker)     │
│  • Risk score panel                         │
│  • uRisk CTA for detailed assessment        │
└─────────────────────────────────────────────┘
```

---

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| **Frontend** | Gradio 6.10 | UI, tabs, file upload |
| **LLM** | Llama 3.1 8B via Groq | Location extraction + report generation |
| **Elevation Data** | ALOS AW3D30 (30m) | Digital Elevation Model |
| **DEM Source** | OpenTopography API | Free satellite DEM download |
| **Watershed** | pysheds | Flow direction, accumulation, catchment |
| **Raster Processing** | rasterio + shapely | DEM clipping to polygon boundary |
| **Geocoding** | Nominatim (OSM) | City name → coordinates + boundary |
| **Map** | Plotly Scattermap | Interactive OSM map with overlays |
| **Deployment** | HuggingFace Spaces | Free cloud hosting |
| **Model Hosting** | Groq Cloud | Fast LLM inference (free tier) |

---

## Input Modes

### 1. Search by City
Ask a natural language question about any Indian city. The LLM extracts the location, downloads the DEM, runs watershed analysis, and generates a risk report.

**Example queries:**
- *"Is Koregaon Park in Pune safe for a residential complex?"*
- *"What is the flood risk for a data center in Bhagalpur?"*
- *"Should I build a warehouse in Whitefield, Bangalore?"*

### 2. Search by Coordinates
Provide exact latitude/longitude and an analysis radius (100m–5km). Useful when you have precise site coordinates from a survey or GPS.

### 3. Upload Site Polygon (GeoJSON)
Upload a `.geojson` file of your exact site boundary. The system:
1. Downloads DEM for the polygon's bounding box
2. **Clips the DEM to the exact polygon** using rasterio mask
3. Computes elevation statistics (min/max/mean) within the site
4. Runs watershed analysis from the polygon centroid
5. Shows the polygon boundary on the map in blue

---

## Risk Scoring Algorithm

The flood risk score (0–100) is computed from three factors:

```
Risk Score = Elevation Score + Catchment Score + Flow Score

Elevation Score  (max 40):
  < 10m   → 40  (very high risk — near sea level)
  < 50m   → 30
  < 100m  → 15
  ≥ 100m  →  5  (low risk — elevated terrain)

Catchment Score  (max 35):
  > 500 km²  → 35  (large upstream area)
  > 100 km²  → 25
  >  10 km²  → 15
  ≤  10 km²  →  5

Flow Score  (max 25):
  > 10,000  → 25  (high flow accumulation)
  >  1,000  → 15
  ≤  1,000  →  5

Season Multiplier:
  Monsoon (Jun–Sep)      → × 1.6
  Post-monsoon (Oct–Dec) → × 1.2
  Dry Season (Jan–May)   → × 0.8

Risk Level:
  ≥ 70 → High
  ≥ 40 → Moderate
  < 40 → Low
```

> **Note:** This is an indicative model based on topographic and hydrological proxies. It does not incorporate measured rainfall, soil permeability, urban drainage infrastructure, or hydrodynamic simulation. For certified assessments, consult a geospatial flood risk specialist.

---

## Data Sources

| Data | Source | Resolution | License |
|---|---|---|---|
| Digital Elevation Model | ALOS AW3D30 via OpenTopography | 30m | Free for research/non-commercial |
| Administrative Boundaries | OpenStreetMap via Nominatim | Vector | ODbL |
| Base Map Tiles | OpenStreetMap | Variable | ODbL |

---

## Pre-cached Cities

The following cities have pre-downloaded DEMs for fast response:

**Metro cities:** Mumbai, Delhi, Bangalore, Hyderabad, Chennai, Kolkata, Pune, Ahmedabad

**Tier 2 cities:** Jaipur, Lucknow, Surat, Bhopal, Patna, Nagpur, Indore, Noida

**Others:** Bandra, Bhagalpur, Sirsa, Haridwar, Dehradun, Srinagar, Thane, Whitefield, Koregaon Park

New cities are downloaded on demand (requires OpenTopography API key, 50 calls/day free tier).

---

## Local Development

```bash
# Clone
git clone https://github.com/rajatchopra91/flood-risk-agent
cd flood-risk-agent

# Create conda environment
conda create -n flood-agent python=3.11 -y
conda activate flood-agent
conda install -c conda-forge rasterio pysheds numpy -y

# Install remaining deps
pip install gradio groq requests geopy python-dotenv shapely folium plotly

# Create .env file
echo "GROQ_API_KEY=your_key_here" > .env
echo "OPENTOPO_API_KEY=your_key_here" >> .env

# Run
python app.py
```

---

## Project Structure

```
flood-risk-agent/
├── app.py              # Main Gradio app + UI
├── tools.py            # Geospatial analysis pipeline
├── dem_downloader.py   # DEM download + pre-cache
├── map_server.py       # Local map server (dev only)
├── agents.py           # Legacy agent loop
├── requirements.txt    # Python dependencies
├── data/dem/           # Cached DEM files (auto-downloaded)
└── README.md
```

---

## Limitations & Disclaimer

This tool provides **indicative assessments only** and should not be used as the sole basis for construction decisions.

Limitations:
- DEM resolution is 30m — may miss micro-topographic features
- Seasonal adjustment is a modelled multiplier, not actual rainfall data
- No soil permeability, land use, or urban drainage data
- Watershed analysis uses D8 flow direction algorithm
- Does not account for existing flood mitigation infrastructure

**For detailed, certified flood risk assessments, contact a geospatial specialist.**

---

## Built With ❤️ by

**Rajat Chopra** — Platform Product Manager | Geospatial AI enthusiast

Built as part of exploring AI-native geospatial tooling for real-world construction risk assessment use cases.

*Presented to [uRisk Consulting](https://www.linkedin.com/company/urisk-consulting/) — specialists in geospatial flood risk assessment.*