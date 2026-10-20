from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    # Database (the ETL; the Parquet and D1 exports run without Postgres)
    database_url: str = ""

    # Environment
    environment: str
    log_level: str = "INFO"
    enable_file_logging: bool = False

    # Feed reader
    feed_reader_max_concurrent_feeds: int = 4
    feed_reader_max_concurrent_entries: int = 50

    # HTTP client
    http_timeout: float = 30.0
    http_max_retries: int = 5
    http_retry_delay: float = 1.0

    # DB retry
    db_max_retries: int = 10
    db_retry_delay: float = 3.0

    # BORME (Boletín Oficial del Registro Mercantil, BOE open data)
    borme_sumario_url: str = (
        "https://www.boe.es/datosabiertos/api/borme/sumario/{fecha}"
    )
    borme_xml_url: str = "https://www.boe.es/diario_borme/xml.php?id={id}"
    borme_max_concurrent: int = 4
    borme_user_agent: str = "licit.es (+https://github.com/pleka-ai/licit)"

    # Cloudflare export (model Parquet on R2, API tables on D1)
    etl_window_days: int = 730
    d1_chunk_rows: int = 50000
    d1_rows_per_insert: int = 40
