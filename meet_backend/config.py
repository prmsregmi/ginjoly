from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    deepgram_api_key: str = ""
    anthropic_api_key: str = ""
    elevenlabs_api_key: str = ""
    openai_api_key: str = ""
    google_email: str = ""
    google_password: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel

    class Config:
        env_file = ".env"


settings = Settings()
