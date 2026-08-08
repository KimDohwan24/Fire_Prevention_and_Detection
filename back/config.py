"""환경변수 로드. 루트의 .env 를 읽는다."""
import os
from pathlib import Path

from dotenv import load_dotenv

# back/ 의 한 단계 위 = 프로젝트 루트
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "fireguard")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_EXPIRES_HOURS = int(os.getenv("JWT_EXPIRES_HOURS", "12"))

APP_PORT = int(os.getenv("APP_PORT", "5000"))
