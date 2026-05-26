cd "j:/DESARROLLO WEB/PROYECTOS/finanzas/backend" && .\venv\Scripts\uvicorn app.main:app --reload --port 8000 > /tmp/backend.log 2>&1 &
echo "Backend PID: $!"