from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = 'postgresql+psycopg://postgres:postgres@localhost:5432/miro_invoice'
    cors_origins: str = 'http://localhost:5173'
    upload_dir: str = './uploads'
    max_file_size_mb: int = 20
    extraction_mode: str = 'demo'
    ollama_url: str = 'http://localhost:11434'
    ollama_model: str = 'llama3.2-vision:11b'
    ollama_timeout: int = 180
    ollama_max_pages: int = 3
    rpa_mode: str = 'mock'
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
settings=Settings()
