from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = BASE_DIR / "resources"


class Settings(BaseSettings):
    app_name: str = "PushToProdSimulation API"
    debug: bool = False
    base_dir: Path = BASE_DIR
    resources_dir: Path = RESOURCES_DIR

    anthropic_api_key: Optional[str] = None
    claude_model: str = "claude-sonnet-4-5"

    model_config = {"env_file": BASE_DIR.parent / ".env", "extra": "ignore"}


settings = Settings()
