#!/bin/bash
cd /app/ai-ml
python3 api_server.py &
FLASK_PID=$!

echo "Flask AI server starting on port 5001 (PID: $FLASK_PID)"

for i in $(seq 1 30); do
    if curl -s http://localhost:5001/health > /dev/null 2>&1; then
        echo "Flask AI server is ready"
        break
    fi
    sleep 1
done

exec java $JAVA_OPTS -jar /app/app.jar
