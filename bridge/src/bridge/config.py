"""Bridge configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    brain_url: str = "http://localhost:5000"
    openfang_url: str = "http://localhost:50051"
    bridge_port: int = 5150
    space_map_path: str = "config/space_agent_map.yaml"
    default_timeout_secs: int = 300
    brain_timeout_secs: int = 2
    min_confidence: float = 0.3

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
