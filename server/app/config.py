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

    # Claude Vision settings
    anthropic_api_key: Optional[str] = None
    claude_model: str = "claude-opus-4-8"
    vision_max_images: int = 20
    vision_low_confidence_threshold: float = 0.6

    model_config = {"env_file": BASE_DIR.parent / ".env", "extra": "ignore"}


settings = Settings()

# Module-level aliases consumed by the Claude Vision check service.
ANTHROPIC_API_KEY = settings.anthropic_api_key
CLAUDE_MODEL = settings.claude_model
