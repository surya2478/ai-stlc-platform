import logging
from app.config import Settings

logger = logging.getLogger(__name__)


def validate_production_config(settings: Settings) -> None:
    """
    Enforces security/configuration checks when app_env is production.
    Raises RuntimeError if a misconfiguration is detected.
    """
    if settings.app_env != "production":
        return

    logger.info("Enforcing production startup validation gates...")

    errors = []
    if not settings.app_secret_key:
        errors.append("APP_SECRET_KEY is empty. A secure secret key must be set in production.")
    else:
        if len(settings.app_secret_key) < 32:
            errors.append("APP_SECRET_KEY must be at least 32 characters long in production.")
        blocklist = {"change-me", "changeme", "secret", "secret_key", "password", "12345678", "dev-secret-key", "development-secret-key"}
        if settings.app_secret_key.lower() in blocklist:
            errors.append(f"APP_SECRET_KEY is set to a forbidden placeholder value: {settings.app_secret_key}")

    if settings.app_debug:
        errors.append("APP_DEBUG is set to True. Debug mode must be disabled in production.")
    if settings.demo_mode:
        errors.append("DEMO_MODE is set to True. Demo mode must be disabled in production.")
    if settings.dev_seed_user_enabled:
        errors.append("DEV_SEED_USER_ENABLED is set to True. Dev user seeding is a development backdoor and must be disabled in production.")

    if errors:
        for error in errors:
            logger.critical(f"Production Config Error: {error}")
        raise RuntimeError(f"Production configuration validation failed: {'; '.join(errors)}")

    logger.info("Production configuration validation passed.")
