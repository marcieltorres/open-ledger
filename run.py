from uvicorn import run

from src.config.settings import settings
from src.api import app as application


def main() -> None:
    app_host = settings.get('UVICORN_HOST', '0.0.0.0')
    app_port = settings.get('UVICORN_PORT', 8000)
    app_num_of_workers = settings.get('UVICORN_WORKERS', 4)
    uvicorn_access_log = True if settings.get("UVICORN_ACCESS_LOG", "False") == "True" else False
    uvicorn_log_level = settings.get("UVICORN_LOG_LEVEL", "info").lower()

    run(
        "run:application",
        host=app_host,
        port=app_port,
        workers=app_num_of_workers,
        log_level=uvicorn_log_level,
        access_log=uvicorn_access_log,
    )


if __name__ == "__main__":
    main()
