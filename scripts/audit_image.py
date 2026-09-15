"""Ensure the runtime credential and local secret files never enter image layers."""

import argparse
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def contains_secret(stream, secret):
    """Scan a file in bounded chunks, including matches crossing chunk boundaries."""
    previous = b""
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            return False
        data = previous + chunk
        if secret in data:
            return True
        previous = data[-max(1, len(secret) - 1) :]


def main():
    """Inspect image metadata and every saved layer without revealing credential values."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    args = parser.parse_args()
    config = json.loads(
        subprocess.check_output(["docker", "compose", "config", "--format", "json"])
    )
    secret = config["services"]["viewer"]["environment"]["DELETE_TOKEN"].encode()
    if not secret:
        raise SystemExit(
            "A nonempty local runtime credential is required for the audit"
        )
    failures = []
    for command in (
        ["docker", "image", "inspect", args.image],
        ["docker", "history", "--no-trunc", "--format", "{{json .}}", args.image],
    ):
        if secret in subprocess.check_output(command):
            failures.append("image metadata or history")
    with tempfile.TemporaryDirectory(prefix="review-image-audit-") as temporary:
        path = Path(temporary) / "image.tar"
        subprocess.run(
            ["docker", "image", "save", "-o", str(path), args.image], check=True
        )
        with tarfile.open(path) as archive:
            manifest = json.load(archive.extractfile("manifest.json"))
            layers = manifest[0]["Layers"]
            for layer in layers:
                with tarfile.open(
                    fileobj=archive.extractfile(layer), mode="r|*"
                ) as contents:
                    for member in contents:
                        name = PurePosixPath(member.name)
                        if (
                            name.name == ".env"
                            or name.name.startswith(".env.")
                            or name.name
                            in {
                                ".delete_pin",
                                "viewer_password.txt",
                                "delete_token.txt",
                            }
                        ):
                            failures.append("secret file: " + member.name)
                        if member.isfile():
                            with contents.extractfile(member) as stream:
                                if contains_secret(stream, secret):
                                    failures.append(
                                        "credential match in: " + member.name
                                    )
    if failures:
        raise SystemExit("Image audit failed (values withheld): " + "; ".join(failures))
    print(
        f"PASS image audit: {len(layers)} layers plus image metadata and history contain no runtime credential or local secret files."
    )


if __name__ == "__main__":
    main()
