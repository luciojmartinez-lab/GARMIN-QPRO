"""Local read-only smoke check for the optional Garmin Connect integration."""

from __future__ import annotations

import argparse
import os
import sys
from getpass import getpass
from pathlib import Path

from garmin_qpro.garmin import (
    DEFAULT_TOKEN_STORE,
    GarminAuthenticationError,
    GarminConnectionError,
    GarminIntegrationUnavailableError,
    GarminResponseError,
    connect_garmin,
)
from garmin_qpro.input import (
    InvalidZipError,
    NoFitFilesError,
    UnsafeZipPathError,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read recent Garmin activities without writing downloads",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--activity-id")
    parser.add_argument(
        "--token-store",
        type=Path,
        default=DEFAULT_TOKEN_STORE,
    )
    return parser.parse_args()


def _connect(token_store: Path):
    try:
        return connect_garmin(token_store=token_store)
    except GarminAuthenticationError:
        email = os.getenv("GARMIN_EMAIL") or input("Garmin email: ").strip()
        password = getpass("Garmin password: ")
        try:
            return connect_garmin(
                token_store=token_store,
                email=email,
                password=password,
                prompt_mfa=lambda: input("Garmin MFA code: ").strip(),
            )
        finally:
            del password


def main() -> int:
    args = _arguments()
    try:
        reader = _connect(args.token_store)
        for activity in reader.list_activities(limit=args.limit):
            print(
                f"{activity.activity_id}\t"
                f"{activity.start_time_local or ''}\t"
                f"{activity.activity_type or ''}\t"
                f"{activity.name}"
            )

        if args.activity_id:
            download = reader.download_original_activity(args.activity_id)
            print(f"ZIP bytes: {download.archive_size}")
            print(f"ZIP SHA-256: {download.archive_sha256}")
            print(f"FIT files: {len(download.sources)}")
            for source in download.sources:
                print(
                    f"FIT: {source.source_name}\t"
                    f"member={source.member_path or ''}\t"
                    f"sha256={source.sha256}"
                )
        return 0
    except (
        GarminIntegrationUnavailableError,
        GarminAuthenticationError,
        GarminConnectionError,
        GarminResponseError,
        InvalidZipError,
        NoFitFilesError,
        UnsafeZipPathError,
    ) as exc:
        print(f"Garmin check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
