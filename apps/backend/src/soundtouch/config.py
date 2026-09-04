from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 7777
    db_path: str = "/data/stoc.db"
    discovery_enabled: bool = True
    discovery_timeout: int = 5
    manual_device_ips: str = ""
    github_repo: str = "grimo77/SoundFlow"
    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    class Config:
        env_prefix = "STOC_"
        env_file = "/data/.env"


settings = Settings()
