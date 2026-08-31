FROM python:3.11-slim

WORKDIR /app

# Install AutoGen + OpenAI
RUN pip install --no-cache-dir "autogen-core==0.7.5" "autogen-agentchat==0.7.5" "openai>=1.0"

# Copy scripts
COPY setup_db.py .
COPY attack_demo.py .
COPY silent_attack_demo.py .
COPY real_llm_attack.py .

# Default: run the real LLM attack demo
# Pass OPENAI_API_KEY via: docker run --rm -e OPENAI_API_KEY=sk-... autogen-poc
CMD ["python", "-u", "real_llm_attack.py"]
