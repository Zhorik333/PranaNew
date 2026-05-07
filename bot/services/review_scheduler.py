"""Background delivery loop for scheduled review request jobs."""

from __future__ import annotations

import asyncio
from typing import Any

from bot.i18n import t
from bot.keyboards.admin import review_request_keyboard
from bot.services.bookings import BookingCompletionError, BookingService, InvalidReviewRequestJob

SCHEDULER_LANGUAGE = "ru"
DEFAULT_REVIEW_SCHEDULER_POLL_SECONDS = 30


class ReviewRequestScheduler:
    """Poll scheduler_jobs and deliver due review request notifications."""

    def __init__(
        self,
        db_pool: Any,
        bot: Any,
        *,
        language: str = SCHEDULER_LANGUAGE,
        poll_interval_seconds: float = DEFAULT_REVIEW_SCHEDULER_POLL_SECONDS,
    ) -> None:
        self.db_pool = db_pool
        self.bot = bot
        self.language = language
        self.poll_interval_seconds = poll_interval_seconds

    async def run_once(self) -> bool:
        """Claim and process one due job. Return True when a job was processed."""

        booking_service = BookingService(self.db_pool)
        try:
            job = await booking_service.claim_due_review_request()
        except InvalidReviewRequestJob as exc:
            await booking_service.restore_scheduler_job_retry(job_id=exc.job_id, error=str(exc))
            return True
        except BookingCompletionError:
            return False
        if job is None:
            return False

        job_id = int(job["job_id"])
        try:
            booking_id = int(job["booking_id"])
            user_id = int(job["user_id"])
            await self.bot.send_message(
                user_id,
                t("review_request", self.language),
                reply_markup=review_request_keyboard(booking_id, language=self.language),
            )
        except BookingCompletionError as exc:
            await booking_service.restore_scheduler_job_retry(job_id=job_id, error=str(exc) or "invalid_review_request_payload")
            return True
        except Exception:
            await booking_service.restore_scheduler_job_retry(job_id=job_id, error="telegram_send_failed")
            return True

        await booking_service.mark_scheduler_job_sent(job_id=job_id)
        return True

    async def run_forever(self) -> None:
        """Continuously process due jobs until cancelled."""

        while True:
            try:
                processed = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                processed = False
            if not processed:
                await asyncio.sleep(self.poll_interval_seconds)


def start_review_request_scheduler(
    db_pool: Any,
    bot: Any,
    *,
    poll_interval_seconds: float = DEFAULT_REVIEW_SCHEDULER_POLL_SECONDS,
) -> asyncio.Task[None]:
    """Start the background review-request scheduler task."""

    scheduler = ReviewRequestScheduler(
        db_pool,
        bot,
        poll_interval_seconds=poll_interval_seconds,
    )
    return asyncio.create_task(scheduler.run_forever())
