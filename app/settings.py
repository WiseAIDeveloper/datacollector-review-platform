"""Runtime configuration; credentials are never supplied during image builds."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

DEFAULT_DATA_ROOT = "/data"


@dataclass(frozen=True)
class Settings:
    """Validated server settings with the credential excluded from representations."""

    root: Path
    database: Path
    log_path: Path
    delete_token: str = field(repr=False)
    host: str = "0.0.0.0"
    port: int = 8080
    projects_root: Path = None
    write_pin_required: bool = True
    static_root: ClassVar[Path] = Path(__file__).resolve().parents[1] / "web"

    @classmethod
    def from_environment(cls, environment=None):
        """Load runtime paths and require a credential only when write PINs are enabled."""
        environment = os.environ if environment is None else environment
        token = environment.get("DELETE_TOKEN", "").strip()
        mode = environment.get("WRITE_PIN_REQUIRED", "true").lower()
        if mode not in {"true", "false", "1", "0"}:
            raise ValueError("WRITE_PIN_REQUIRED must be true or false")
        write_pin_required = mode in {"true", "1"}
        if write_pin_required and not token:
            raise ValueError("Set DELETE_TOKEN in the runtime environment")
        port = int(environment.get("PORT", "8080"))
        if not 0 <= port <= 65535:
            raise ValueError("PORT must be between 0 and 65535")
        return cls(
            root=Path(environment.get("DATA_ROOT", DEFAULT_DATA_ROOT)).resolve(),
            database=Path(environment.get("INGESTION_DB", "/state/ingestion.sqlite")),
            log_path=Path(environment.get("INGESTION_LOG", "/logs/ingestion.jsonl")),
            delete_token=token,
            write_pin_required=write_pin_required,
            host=environment.get("HOST", "0.0.0.0"),
            port=port,
            projects_root=(
                Path(environment["PROJECTS_ROOT"]).resolve()
                if environment.get("PROJECTS_ROOT")
                else None
            ),
        )
