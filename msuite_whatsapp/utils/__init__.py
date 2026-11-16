"""
Deprecated location — kept as a backward-compatible re-export layer.

Account resolution and number formatting utilities:
  - `repositories.account_repository` (get_whatsapp_account)
  - `msuite_core.utils.phone` (format_number)
"""

from msuite_whatsapp.utils.phone import format_number
from msuite_whatsapp.queries.account_repository import get_whatsapp_account
