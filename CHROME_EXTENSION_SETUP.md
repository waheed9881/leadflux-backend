# Chrome Extension Setup (Google Maps + LinkedIn)

The extension lives in `python-scrapper/chrome-extension/` and supports:
- Google Maps capture + import to backend
- LinkedIn email finder (legacy)

## Install (Unpacked)

1. Open `chrome://extensions/`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select `python-scrapper/chrome-extension/`
5. Pin the extension to your toolbar (optional)

## Configure

1. Click the extension icon
2. Set **API URL** to your backend (default: `http://localhost:8002`)
3. Click **Save Settings**

## Google Maps Workflow

1. Open `https://www.google.com/maps`
2. Search for a niche + location
3. Open the extension popup → **Google Maps Capture**
4. Click **Start**
5. Scroll the results list to collect more items
6. Click **Import to Backend**
7. In the web app: `Google Maps` → `Extension Imports` → **Refresh**

## Download As Zip (Optional)

If your backend is running, you can download a ready-to-unzip package:
- `GET http://localhost:8002/api/extension/download` (downloads `leadflux-chrome-extension.zip`)

