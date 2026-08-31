import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from seathunter.config.manager import ConfigManager
from seathunter.models.booking_result import BookingResult
from seathunter.models.schedule import DateMapping, Schedule
from seathunter.scheduler.one_shot import (
    booking_open_at,
    collect_plan_ids,
    target_date_for_run,
)


class OneShotSelectionTests(unittest.TestCase):
    def test_collects_weekday_and_date_plans_without_duplicates(self):
        target = datetime(2026, 9, 2)  # Wednesday
        schedules = [
            Schedule(
                mode="weekdays",
                target_weekdays=[3],
                plan_ids=["primary", "backup"],
            ),
            Schedule(
                mode="dates",
                mappings=[DateMapping("2026-09-02", ["backup", "special"])],
            ),
            Schedule(
                mode="weekdays",
                enabled=False,
                target_weekdays=[3],
                plan_ids=["disabled"],
            ),
        ]

        self.assertEqual(
            collect_plan_ids(schedules, target),
            ["primary", "backup", "special"],
        )

    def test_target_date_is_two_days_after_run_date(self):
        now = datetime(2026, 8, 31, 19, 45, 30)
        self.assertEqual(target_date_for_run(now), datetime(2026, 9, 2))

    def test_booking_open_time_uses_run_date(self):
        now = datetime(2026, 8, 31, 19, 45, 30)
        self.assertEqual(
            booking_open_at(now, "20:00:00"),
            datetime(2026, 8, 31, 20, 0, 0),
        )

    def test_invalid_booking_open_time_is_rejected(self):
        with self.assertRaises(ValueError):
            booking_open_at(datetime(2026, 8, 31), "8pm")


class CredentialOverrideTests(unittest.TestCase):
    def test_environment_credentials_override_file_without_saving(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write(
                    "user:\n"
                    "  login_name: file-user\n"
                    "  password: file-password\n"
                )

            manager = ConfigManager(config_path)
            manager.load()
            with patch.dict(
                os.environ,
                {
                    "SEATHUNTER_LOGIN_NAME": "secret-user",
                    "SEATHUNTER_PASSWORD": "secret-password",
                },
                clear=False,
            ):
                self.assertEqual(
                    manager.get_user_info(),
                    {"login_name": "secret-user", "password": "secret-password"},
                )

            with open(config_path, "r", encoding="utf-8") as config_file:
                self.assertNotIn("secret-password", config_file.read())


class BookingResultTests(unittest.TestCase):
    def test_existing_reservation_is_an_idempotent_success(self):
        result = BookingResult.from_api_response(
            {"CODE": "ParamError", "MESSAGE": "已有预约，请勿重复预约！"}
        )

        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
