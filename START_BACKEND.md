# How to Start the Backend (Python FastAPI)

## Prerequisites
Make sure you have:
- Python 3.8+ installed
- All dependencies installed: `pip install -r requirements.txt`
- `.env` file configured with `DATABASE_URL`

## Start the Backend Server

### Option 1: Using main.py (Recommended)
```bash
cd python-scrapper
python main.py
```

The server will start on: **http://localhost:8002**

### Option 2: Using Uvicorn directly
```bash
cd python-scrapper
uvicorn app.api.server:app --host 0.0.0.0 --port 8002 --reload
```

### Option 3: Using the PORT environment variable
```bash
cd python-scrapper
$env:PORT=8002  # PowerShell
python main.py
```

## Verify Backend is Running

1. Open browser: http://localhost:8002/docs
2. You should see the FastAPI Swagger documentation
3. Or test: http://localhost:8002/health

## Default Ports
- **Port 8002**: Default backend port

## Stop the Server
Press `Ctrl + C` in the terminal

