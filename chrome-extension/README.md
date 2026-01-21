# LeadFlux Chrome Extension

This Chrome extension supports:
- Google Maps: capture listings while you scroll and import them into the LeadFlux backend
- LinkedIn: email finder widget (legacy)

## Install (Unpacked)

1. Open `chrome://extensions/`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select `python-scrapper/chrome-extension/`

## Configure

Open the extension popup and set:
- **API URL** (default): `http://localhost:8002`

## Google Maps Capture

1. Open `https://www.google.com/maps`
2. Search for a niche + location
3. Open the extension popup → **Google Maps Capture**
4. Click **Start** and scroll the results list
5. Optional: click **Fetch Details** to open listings and capture website/phone
6. Click **Import to Backend**

In the web app: `Google Maps` → `Extension Imports` → click `Refresh`.

## Backend Endpoints Used

- `POST /api/google-maps/import`
- `POST /api/google-maps/extract-contacts` (optional enrichment)

