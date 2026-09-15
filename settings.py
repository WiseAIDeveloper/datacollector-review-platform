"""Runtime configuration; credentials are never supplied during image builds."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Validated server settings with the credential excluded from representations."""

    root: Path
    database: Path
    log_path: Path
    delete_token: str = field(repr=False)
    host: str = "0.0.0.0"
    port: int = 8080
    static_root: Path = Path(__file__).resolve().parent

    @classmethod
    def from_environment(cls, environment=None):
        """Load runtime paths and require a nonempty deletion credential."""
        environment = os.environ if environment is None else environment
        token = environment.get("DELETE_TOKEN", "").strip()
        if not token:
            raise ValueError("Set DELETE_TOKEN in the runtime environment")
        port = int(environment.get("PORT", "8080"))
        if not 0 <= port <= 65535:
            raise ValueError("PORT must be between 0 and 65535")
        return cls(
            root=Path(environment.get("DATA_ROOT", "/data")).resolve(),
            database=Path(environment.get("INGESTION_DB", "/state/ingestion.sqlite")),
            log_path=Path(environment.get("INGESTION_LOG", "/logs/ingestion.jsonl")),
            delete_token=token,
            host=environment.get("HOST", "0.0.0.0"),
            port=port,
        )
