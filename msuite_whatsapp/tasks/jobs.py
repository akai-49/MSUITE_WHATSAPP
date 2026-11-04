"""What the scheduler runs."""

from msuite_whatsapp.api.v1.app import bulk_messaging
from msuite_whatsapp.services.accounts import messaging_limit_service
from msuite_whatsapp.services.analytics import sync
from msuite_whatsapp.services.calls import call_service


def schedule_bulk_messages() -> None:
	bulk_messaging.schedule_bulk_messages()


def sweep_stale_calls() -> None:
	call_service.sweep_stale_calls()


def sync_all_accounts() -> None:
	sync.sync_all_accounts()


def refresh_all() -> None:
	messaging_limit_service.refresh_all()


def sync_daily_tasks() -> None:
	sync.sync_daily_tasks()
