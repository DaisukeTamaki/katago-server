from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "KATAGO_"}

    katago_binary: str = "katago"
    analysis_config: Path = Path("config/analysis.cfg")
    model_path: Path = Path("models/default.bin.gz")

    board_size_x: int = 19
    board_size_y: int = 19
    default_komi: float = 6.5
    default_rules: str = "tromp-taylor"

    report_during_search_every: float = 0.2

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"


settings = Settings()
