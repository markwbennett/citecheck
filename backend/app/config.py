from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    from_email: str
    frontend_url: str

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()
