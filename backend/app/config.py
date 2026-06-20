"""
Application configuration loaded from environment variables.
All secrets are read from .env — never hardcoded here.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "STLC Automation Platform"
    app_version: str = "0.1.0"
    app_env: Literal["local", "staging", "production"] = "local"
    app_debug: bool = False
    app_secret_key: str = Field(default="change-me", min_length=8)
    allowed_origins: str = "http://localhost:3000"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql://user:password@db:5432/stlc_agents"

    # Connection pool tuning (ignored when db_pool_enabled=False / NullPool)
    db_pool_enabled: bool = True
    db_pool_size: int = 10              # base number of persistent connections
    db_pool_max_overflow: int = 20      # extra connections above pool_size under load
    db_pool_timeout: int = 30           # seconds to wait for a connection before error
    db_pool_recycle: int = 1800         # seconds before a connection is recycled (30 min)
    db_pool_pre_ping: bool = True       # verify connection liveness before checkout

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"

    # ── LLM Provider ─────────────────────────────────────────────────────────
    default_llm_provider: Literal[
        "ollama",
        "openai",
        "groq",
        "google_gemini",
        "openrouter",
        "huggingface",
        "together",
        "cerebras",
        "mistral",
    ] = "ollama"
    default_llm_model: str = "llama3.1"

    # GAP-1: Vision model for UI screenshot analysis.
    # Ollama: a multimodal model such as "llava" or "qwen2.5vl" (must be pulled).
    # OpenAI-compatible: any vision-capable model (e.g. "gpt-4o-mini").
    default_vision_model: str = "llava"

    # Ollama
    ollama_base_url: str = "http://ollama:11434"

    # OpenAI
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # Groq — fast open-source LLM inference
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"

    # Together AI — free-tier open-source LLMs (Standby #1)
    together_api_key: str = ""
    together_base_url: str = "https://api.together.xyz/v1"
    together_model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free"

    # Cerebras — ultra-fast LLaMA inference (Standby #2)
    cerebras_api_key: str = ""
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    cerebras_model: str = "llama-3.3-70b"

    # Mistral AI — Codestral free for code tasks (Standby #3)
    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai/v1"
    mistral_model: str = "codestral-latest"

    # Google Gemini
    google_api_key: str = ""
    google_gemini_api_key: str = ""
    gemini_api_key: str = ""
    google_gemini_model: str = "gemini-2.0-flash"

    # OpenRouter — multi-model aggregator (Standby #4)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"

    # Hugging Face Inference (Standby #6 — open-source fallback)
    huggingface_api_key: str = ""
    huggingfacehub_api_token: str = ""
    huggingface_model: str = "meta-llama/Llama-3.1-8B-Instruct"

    # ── LLM Reliability ───────────────────────────────────────────────────────
    llm_max_retries: int = 3
    llm_retry_backoff_seconds: float = 1.0
    llm_circuit_breaker_failures: int = 5
    llm_circuit_breaker_reset_seconds: int = 120

    # ── Jira ─────────────────────────────────────────────────────────────────
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = ""
    jira_simulation_mode: bool = True
    jira_webhook_secret: str = ""

    # Test execution
    real_test_execution: bool = False
    run_agents_synchronously: bool = True
    dev_seed_user_enabled: bool = False
    dev_seed_user_email: str = ""
    dev_seed_user_password: str = ""
    demo_mode: bool = False

    # ── Security & AI Hardening ──────────────────────────────────────────────
    prompt_guard_enabled: bool = True
    allowed_code_analysis_paths: str = "c:\\Test_AI_Agents\\Test_AI_Agents\\stlc-platform"

    # ── File Storage ──────────────────────────────────────────────────────────
    file_storage_path: str = "/app/storage"
    max_upload_size_mb: int = 25

    # ── Data Retention ────────────────────────────────────────────────────────
    retention_agent_logs_days: int = 90       # archive agent run logs older than N days
    retention_rag_events_days: int = 180      # purge RAG retrieval audit events older than N days
    retention_uploaded_files_days: int = 365  # flag uploaded docs for cleanup after N days

    # ── RAG / Embeddings ──────────────────────────────────────────────────────
    rag_enabled: bool = False
    embedding_provider: Literal["sentence_transformers", "openai", "huggingface"] = "sentence_transformers"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384
    embedding_batch_size: int = 32
    rag_top_k_candidates: int = 20
    rag_top_k_context: int = 5
    rag_semantic_weight: float = 0.65
    rag_keyword_weight: float = 0.35

    @property
    def allowed_code_analysis_paths_list(self) -> list[str]:
        import os
        paths = []
        if os.path.exists("/repo"):
            paths.append(os.path.realpath("/repo"))
        if os.path.exists("/app"):
            paths.append(os.path.realpath("/app"))

        if self.allowed_code_analysis_paths:
            for p in self.allowed_code_analysis_paths.split(","):
                p = p.strip()
                if p:
                    try:
                        paths.append(os.path.realpath(p))
                    except Exception:
                        pass
        return list(set(paths))

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        if self.app_env == "production":
            if not self.app_secret_key or self.app_secret_key == "change-me":
                raise ValueError("APP_SECRET_KEY is set to the default value 'change-me' in production environment.")
            if len(self.app_secret_key) < 32:
                raise ValueError("APP_SECRET_KEY must be at least 32 characters long in production.")
            blocklist = {"change-me", "changeme", "secret", "secret_key", "password", "12345678", "dev-secret-key", "development-secret-key"}
            if self.app_secret_key.lower() in blocklist:
                raise ValueError(f"APP_SECRET_KEY uses a forbidden placeholder value in production: {self.app_secret_key}")
            if self.dev_seed_user_enabled:
                raise ValueError("DEV_SEED_USER_ENABLED is set to True. Seeding dev users must be disabled in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — call this everywhere instead of instantiating directly."""
    return Settings()
