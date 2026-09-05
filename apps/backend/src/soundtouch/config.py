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
    # Fixed redirect URI for Spotify OAuth. Spotify only allows http:// with
    # 127.0.0.1 (not LAN IPs), so this defaults to loopback. Override if needed.
    spotify_redirect_uri: str = "http://127.0.0.1:7777/api/spotify/callback"

    class Config:
        env_prefix = "STOC_"
        env_file = "/data/.env"


settings = Settings()
