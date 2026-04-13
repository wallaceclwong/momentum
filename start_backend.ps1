# Start backend API server from correct directory
Set-Location "C:\Users\ASUS\Momentum\sp500-momentum"
C:\Users\ASUS\Momentum\.venv\Scripts\uvicorn.exe backend.main:app --host 0.0.0.0 --port 8000
