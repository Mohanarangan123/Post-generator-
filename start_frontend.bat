@echo off
echo ============================================================
echo Starting LinkedIn Post Generator Frontend
echo ============================================================
echo.

cd frontend

echo Checking Python environment...
python --version
echo.

echo ============================================================
echo Starting Streamlit Frontend
echo ============================================================
echo.
echo Frontend will open automatically in your browser
echo Or visit: http://localhost:8501
echo.
echo Press CTRL+C to stop the server
echo.

streamlit run app.py
