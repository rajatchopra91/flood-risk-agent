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

AI-powered indicative flood risk assessment for construction sites across India.

## Features
- Search by city name, coordinates, or upload a site polygon (GeoJSON)
- Seasonal risk scenarios (Monsoon, Post-monsoon, Dry Season)
- Leaflet map with OSM administrative boundaries
- DEM clipping for polygon-based analysis
- AI report powered by Llama 3 via Groq

## Data Sources
- Elevation: ALOS AW3D30 (30m) via OpenTopography
- Boundaries: OpenStreetMap via Nominatim
- LLM: Llama 3.1 8B via Groq API

## Disclaimer
Indicative tool only. For certified assessments contact a geospatial specialist.
