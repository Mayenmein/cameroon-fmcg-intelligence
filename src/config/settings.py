# Pydantic settings, loads .env
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    """Application settings"""
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # Database — read from .env, no defaults
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    # API keys — read from .env, no defaults
    wb_api_key: str
    comtrade_api_key: str

    # Directories (derived from PROJECT_ROOT)
    data_raw_dir: Path = PROJECT_ROOT / "data" / "raw"
    data_interim_dir: Path = PROJECT_ROOT / "data" / "interim"
    data_processed_dir: Path = PROJECT_ROOT / "data" / "processed"
    logs_dir: Path = PROJECT_ROOT / "logs"

    comtrade_raw_path: Path = PROJECT_ROOT / "data" / "raw" / "comtrade"
    wfp_raw_path: Path = PROJECT_ROOT / "data" / "raw" / "wfp"
    gadm_raw_path: Path = PROJECT_ROOT / "data" / "raw" / "gadm"

    comtrade_processed_path: Path = PROJECT_ROOT / "data" / "processed" / "comtrade"
    wfp_processed_path: Path = PROJECT_ROOT / "data" / "processed" / "wfp"
    gadm_processed_path: Path = PROJECT_ROOT / "data" / "processed" / "gadm"

    comtrade_interim_path: Path = PROJECT_ROOT / "data" / "interim" / "comtrade"
    wfp_interim_path: Path = PROJECT_ROOT / "data" / "interim" / "wfp"
    gadm_interim_path: Path = PROJECT_ROOT / "data" / "interim" / "gadm"

    dim_region_path: Path = PROJECT_ROOT / "data" / "processed" / "gadm" / "dim_region.csv"

    @property
    def database_url(self) -> str:
        """Return the SQLAlchemy database URL."""
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

settings = Settings()