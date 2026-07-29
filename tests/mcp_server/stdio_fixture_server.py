"""Synthetic STDIO server used only by MCP transport tests."""

from garmin_qpro.mcp_server.server import create_mcp_server


class SyntheticService:
    def list_garmin_activities(self, *, start=0, limit=10):
        return {
            "activities": (
                {
                    "activity_id": "42",
                    "name": "Synthetic Run",
                    "activity_type": "running",
                    "start_time_local": "2026-07-28 10:00:00",
                    "duration_s": 60.0,
                    "elapsed_duration_s": 65.0,
                    "distance_m": 200.0,
                },
            ),
            "count": 1,
            "start": start,
            "limit": limit,
        }

    def inspect_garmin_activity(
        self,
        *,
        activity_id,
        verify_crc=True,
        force_refresh=False,
    ):
        return {
            "activity_id": str(activity_id),
            "container_name": f"garmin-{activity_id}.zip",
            "archive_sha256": "a" * 64,
            "archive_size": 100,
            "fit_count": 1,
            "sources": (
                {
                    "source_name": "activity.fit",
                    "container_name": f"garmin-{activity_id}.zip",
                    "member_path": "activity.fit",
                    "sha256": "b" * 64,
                    "workout_name": "EB1 - Carrera - 1",
                    "workout_name_field": "workout.workout_name",
                    "sport_profile_name": "Carrera",
                    "sport": "running",
                    "sub_sport": "generic",
                    "qpro_key": "ENT",
                    "resolution_source": "workout_name",
                    "requires_user_choice": False,
                    "crc_checked": verify_crc,
                    "decoder_error_count": 0,
                },
            ),
        }

    def convert_garmin_activity(
        self,
        *,
        activity_id,
        explicit_qpro_key=None,
        verify_crc=True,
        force_refresh=False,
    ):
        row = tuple(["ENT", *("" for _ in range(21)), "'000"])
        tsv = "\t".join(row)
        return {
            "activity_id": str(activity_id),
            "container_name": f"garmin-{activity_id}.zip",
            "archive_sha256": "a" * 64,
            "archive_size": 100,
            "success_count": 1,
            "failure_count": 0,
            "results": (
                {
                    "source_name": "activity.fit",
                    "container_name": f"garmin-{activity_id}.zip",
                    "member_path": "activity.fit",
                    "sha256": "b" * 64,
                    "qpro_key": explicit_qpro_key or "ENT",
                    "resolution_source": (
                        "explicit_qpro_key"
                        if explicit_qpro_key
                        else "workout_name"
                    ),
                    "workout_name": "EB1 - Carrera - 1",
                    "sport_profile_name": "Carrera",
                    "metric_family": "running",
                    "metrics": {},
                    "row_values": row,
                    "tsv": tsv,
                    "column_count": 23,
                    "tab_count": 22,
                    "requires_manual_review": False,
                },
            ),
            "failures": (),
            "tsv": tsv,
        }


if __name__ == "__main__":
    create_mcp_server(SyntheticService()).run(transport="stdio")
