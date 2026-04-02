FROM python:3.12-slim
WORKDIR /app
RUN pip install fastapi uvicorn httpx
COPY vibemind_mcp.py .
CMD ["uvicorn", "vibemind_mcp:app", "--host", "0.0.0.0", "--port", "8809"]
