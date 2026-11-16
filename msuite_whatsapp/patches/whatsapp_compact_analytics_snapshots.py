"""
Backfill `snapshot_key` on every existing WhatsApp Analytics Snapshot row,
deduplicate to 1 row per (whatsapp_account, metric_type, granularity), and add
the DB unique constraint.

Mirrors `ads_dedupe_and_key_ad_insight.py` and `social_dedupe_and_key_social_insight.py`.

Why:
  1. Previously, `_save_snapshot` always inserted a new row on each sync run.
  2. The window moves every day, causing unbounded table growth.
  3. The target data model is exactly 1 snapshot row per
     (whatsapp_account, metric_type, granularity) holding the latest window.

This patch:
  1. Reloads the DocType to ensure `snapshot_key` column exists.
  2. Cleans up any duplicate rows that already have `snapshot_key` populated.
  3. Computes `snapshot_key = make_key(account, metric_type, granularity)` for
     all un-keyed legacy rows.
  4. Keeps the newest row per identity key (by synced_at desc, modified desc)
     and deletes stale rows in batches.
  5. Backfills `snapshot_key` onto the retained row.
  6. Adds a DB unique constraint on `snapshot_key`.
"""

import frappe

from msuite_whatsapp.constants import INSIGHT_DELETE_BATCH
from msuite_whatsapp.utils.insight_keys import delete_in_batches, make_key
from msuite_whatsapp.constants import AnalyticsGranularity


def execute() -> None:
	"""Execute WhatsApp Analytics Snapshot deduplication and unique key backfill.

	Args:
		None.

	Returns:
		None.

	Raises:
		Exception: If schema reload or database operation fails.

	Side effects:
		Deletes duplicate snapshot rows, backfills snapshot_key, commits
		transactions, and adds a unique constraint to tabWhatsApp Analytics Snapshot.
	"""
	frappe.reload_doc("whatsapp", "doctype", "whatsapp_analytics_snapshot")

	# Clean up any existing duplicates that already have snapshot_key populated
	duplicate_keys = frappe.db.sql(
		"""
		SELECT snapshot_key
		FROM `tabWhatsApp Analytics Snapshot`
		WHERE snapshot_key IS NOT NULL AND snapshot_key != ''
		GROUP BY snapshot_key
		HAVING COUNT(*) > 1
	""",
		as_dict=True,
	)

	for d in duplicate_keys:
		key = d["snapshot_key"]
		rows_with_key = frappe.get_all(
			"WhatsApp Analytics Snapshot",
			filters={"snapshot_key": key},
			fields=["name", "synced_at", "modified"],
			order_by="synced_at desc, modified desc",
		)
		if len(rows_with_key) > 1:
			stale_names = [r.name for r in rows_with_key[1:]]
			delete_in_batches("WhatsApp Analytics Snapshot", stale_names, commit=False)

	frappe.db.commit()

	last_name = ""
	keyed = 0
	deleted = 0
	superseded = 0

	while True:
		conditions = ["(snapshot_key IS NULL OR snapshot_key = '')"]
		params = []
		if last_name:
			conditions.append("name > %s")
			params.append(last_name)

		where_clause = f"WHERE {' AND '.join(conditions)}"
		query = f"""
			SELECT name, whatsapp_account, metric_type, granularity, synced_at, modified, creation
			FROM `tabWhatsApp Analytics Snapshot`
			{where_clause}
			ORDER BY name ASC
			LIMIT %s
		"""
		params.append(INSIGHT_DELETE_BATCH)

		batch = frappe.db.sql(query, tuple(params), as_dict=True)
		if not batch:
			break

		for r in batch:
			key = make_key(
				r.whatsapp_account,
				r.metric_type,
				r.granularity or AnalyticsGranularity.DAY,
			)

			existing = frappe.db.get_value(
				"WhatsApp Analytics Snapshot",
				{"snapshot_key": key},
				["name", "synced_at", "modified", "creation"],
				as_dict=True,
			)

			if existing and existing.name != r.name:
				r_ts = (
					str(r.get("synced_at") or ""),
					str(r.get("modified") or ""),
					str(r.get("creation") or ""),
					str(r.name),
				)
				ex_ts = (
					str(existing.get("synced_at") or ""),
					str(existing.get("modified") or ""),
					str(existing.get("creation") or ""),
					str(existing.name),
				)
				if r_ts > ex_ts:
					delete_in_batches("WhatsApp Analytics Snapshot", [existing.name], commit=False)
					frappe.db.set_value(
						"WhatsApp Analytics Snapshot",
						r.name,
						"snapshot_key",
						key,
						update_modified=False,
					)
					deleted += 1
					keyed += 1
				else:
					delete_in_batches("WhatsApp Analytics Snapshot", [r.name], commit=False)
					deleted += 1
			else:
				frappe.db.set_value(
					"WhatsApp Analytics Snapshot",
					r.name,
					"snapshot_key",
					key,
					update_modified=False,
				)
				keyed += 1

		frappe.db.commit()
		last_name = batch[-1].name
		if len(batch) < INSIGHT_DELETE_BATCH:
			break

	frappe.db.commit()

	# Only safe once every retained row is keyed and duplicates are removed
	frappe.db.add_unique("WhatsApp Analytics Snapshot", ["snapshot_key"])

	print(
		f"whatsapp_compact_analytics_snapshots: keyed {keyed} rows, "
		f"removed {deleted} duplicate rows, "
		f"removed {superseded} rows superseded by a concurrently-synced fresh row"
	)
