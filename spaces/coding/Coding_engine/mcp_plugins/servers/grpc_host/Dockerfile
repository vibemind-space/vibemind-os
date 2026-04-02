# Dockerfile für EventFix gRPC Host Server
FROM python:3.11-slim

WORKDIR /app

# System-Abhängigkeiten installieren
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python-Abhängigkeiten kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Protobuf-Dateien kompilieren
COPY proto/ ./proto/
RUN python -m grpc_tools.protoc -I./proto --python_out=. --grpc_python_out=. ./proto/agent_service.proto

# Quellcode kopieren
COPY src/ ./src/
COPY grpc_server.py .

# Verzeichnisse erstellen
RUN mkdir -p /app/logs /app/tasks

# Port freigeben
EXPOSE 50051 8000

# Health Check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:50051'); grpc.channel_ready_future(channel).result(timeout=5)"

# Server starten
CMD ["python", "grpc_server.py"]
