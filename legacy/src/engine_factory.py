from src.katago_client import KataGoClient


def build_default_engine() -> KataGoClient:
    return KataGoClient.from_environment()
