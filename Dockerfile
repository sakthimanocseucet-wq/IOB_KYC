# Stage 1: Build the JAR
FROM maven:3.9-eclipse-temurin-17 AS builder
WORKDIR /app
COPY backend/pom.xml backend/pom.xml
RUN cd backend && mvn dependency:go-offline -q
COPY backend/src backend/src
RUN cd backend && mvn clean package -DskipTests -q

# Stage 2: Runtime
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends default-jre-headless libgl1 libglib2.0-0 libzbar0 libegl1 libgles2 wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ai-ml/requirements.txt ai-ml/requirements.txt
RUN pip3 install --no-cache-dir --no-compile -r ai-ml/requirements.txt && \
    rm -rf /root/.cache/pip /tmp/*

# Download haarcascade files for opencv-python-headless
RUN python3 -c "import cv2, os; print(cv2.data.haarcascades)" && \
    wget -q https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml -O /usr/local/lib/python3.11/site-packages/cv2/data/haarcascade_frontalface_default.xml && \
    wget -q https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_eye.xml -O /usr/local/lib/python3.11/site-packages/cv2/data/haarcascade_eye.xml && \
    echo "Haarcascade files downloaded"

COPY ai-ml/ ai-ml/
COPY --from=builder /app/backend/target/kyc-system-1.0.0.jar app.jar

ENV JAVA_OPTS="-Xms256m -Xmx768m -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -XX:+UseStringDeduplication"
ENV FILE_UPLOAD_DIR=./uploads
ENV SERVER_PORT=8080
EXPOSE 8080 5001

CMD ["sh", "-c", "python3 /app/ai-ml/api_server.py 2>&1 & sleep 30 && java $JAVA_OPTS -jar /app/app.jar"]
