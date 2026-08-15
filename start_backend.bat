@echo off
echo ============================================================
echo Starting LinkedIn Post Generator Backend
echo ============================================================
echo.

cd backend

echo Checking Python environment...
python --version
echo.

echo ============================================================
echo Starting FastAPI Backend Server
echo ============================================================
echo.
echo Backend will be available at: http://localhost:8000
echo API Documentation at: http://localhost:8000/docs
echo.
echo Press CTRL+C to stop the server
echo.

uvicorn app.main:app --reload --port 8000
