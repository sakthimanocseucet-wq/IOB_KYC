# Stage 1: Build the JAR
FROM maven:3.9-eclipse-temurin-17 AS builder
WORKDIR /app
COPY backend/pom.xml backend/pom.xml
RUN cd backend && mvn dependency:go-offline -q
COPY backend/src backend/src
RUN cd backend && mvn clean package -DskipTests -q

# Stage 2: Runtime
FROM eclipse-temurin:17-jre

RUN apt-get update && \
    apt-get install -y python3 python3-pip libgl1 libglib2.0-0 libzbar0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ai-ml/requirements.txt ai-ml/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r ai-ml/requirements.txt || \
    pip3 install --break-system-packages --no-cache-dir flask flask-cors opencv-python-headless pyzbar numpy Pillow requests python-dotenv

COPY ai-ml/ ai-ml/
COPY --from=builder /app/backend/target/kyc-system-1.0.0.jar app.jar

ENV JAVA_OPTS="-Xms256m -Xmx512m"
ENV FILE_UPLOAD_DIR=./uploads
ENV SERVER_PORT=8080
EXPOSE 8080 5001

CMD ["sh", "-c", "python3 /app/ai-ml/api_server.py 2>&1 & sleep 10 && java $JAVA_OPTS -jar /app/app.jar"]
