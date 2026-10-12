"""Download selected objects from a locally published MinIO server.

This utility only uses Python's standard library.  On the Docker host it reads
the MinIO credentials from the already-running server container, then signs
S3 GetObject requests with AWS Signature Version 4.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


def docker_env(container: str, variable: str) -> str:
    result = subprocess.run(
        ["docker", "exec", container, "printenv", variable],
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if not value:
        raise RuntimeError(f"{variable} is empty in Docker container {container!r}")
    return value


def sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret: str, stamp: str, region: str, service: str) -> bytes:
    date_key = sign(("AWS4" + secret).encode("utf-8"), stamp)
    region_key = sign(date_key, region)
    service_key = sign(region_key, service)
    return sign(service_key, "aws4_request")


def signed_get(
    endpoint: str,
    bucket: str,
    object_key: str,
    access_key: str,
    secret_key: str,
    region: str,
):
    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid endpoint: {endpoint!r}")

    timestamp = dt.datetime.now(dt.timezone.utc)
    amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = timestamp.strftime("%Y%m%d")
    canonical_uri = "/" + quote(bucket, safe="") + "/" + quote(object_key, safe="/~")
    payload_hash = hashlib.sha256(b"").hexdigest()
    canonical_headers = (
        f"host:{parsed.netloc}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(
        ["GET", canonical_uri, "", canonical_headers, signed_headers, payload_hash]
    )
    scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(
        signing_key(secret_key, date_stamp, region, "s3"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    request = Request(
        f"{endpoint.rstrip('/')}{canonical_uri}",
        headers={
            "Authorization": authorization,
            "Host": parsed.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        },
        method="GET",
    )
    return urlopen(request, timeout=120)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download selected MinIO objects using Docker-hosted credentials.")
    parser.add_argument("--keys-file", required=True, type=Path, help="UTF-8 text file with one object key per line")
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:9000")
    parser.add_argument("--bucket", default="farmiq-media")
    parser.add_argument("--docker-container", default="edge-layer-minio-1")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    keys = [line.strip() for line in args.keys_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not keys:
        raise SystemExit("The keys file is empty.")
    if len({Path(key).name for key in keys}) != len(keys):
        raise SystemExit("Object basenames must be unique for a flat destination directory.")

    access_key = docker_env(args.docker_container, "MINIO_ROOT_USER")
    secret_key = docker_env(args.docker_container, "MINIO_ROOT_PASSWORD")
    args.destination.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    for number, object_key in enumerate(keys, start=1):
        output = args.destination / Path(object_key).name
        temporary = output.with_suffix(output.suffix + ".part")
        try:
            with signed_get(args.endpoint, args.bucket, object_key, access_key, secret_key, args.region) as response:
                with temporary.open("wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
            temporary.replace(output)
            print(f"[{number}/{len(keys)}] {output.name}")
        except (HTTPError, URLError, OSError, ValueError) as error:
            temporary.unlink(missing_ok=True)
            failures.append(f"{object_key}: {error}")
            print(f"[{number}/{len(keys)}] FAILED {object_key}: {error}", file=sys.stderr)

    if failures:
        raise SystemExit(f"{len(failures)} object(s) failed to download.")


if __name__ == "__main__":
    main()
