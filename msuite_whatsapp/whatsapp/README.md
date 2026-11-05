# WhatsApp Module

## Analytics and Compaction

### Snapshot Storage and Compaction (`whatsapp/analytics/sync.py`)
- **Compacted snapshots**: `_save_snapshot` upserts exactly 1 row per `(whatsapp_account, metric_type, granularity)` using deterministic `snapshot_key = make_key(whatsapp_account, metric_type, granularity)`.
- **In-place rolling updates**: Subsequent syncs overwrite `period_start`, `period_end`, `raw_data`, and `synced_at` on the existing row. The daily data points are already nested within `raw_data`, preventing unbounded table growth.
- **Unique DB index**: Patch `whatsapp_compact_analytics_snapshots` dedupes legacy rows (retaining the most recently modified/synced row per key) and establishes a real DB unique constraint on `snapshot_key`.
- **Concurrency handling**: If concurrent workers race to insert for the same key, `_save_snapshot` catches `(DuplicateEntryError, UniqueValidationError)` and falls back to updating the existing record.
- **Defensive cleanup**: `cleanup_old_snapshots()` is reduced from deleting by shifting window dates to a defensive check against duplicate keys.

### Marketing Messages Retention (`whatsapp/analytics/mm_sync.py`)
- Marketing metric rows (`WhatsApp Marketing Metric`) are recorded per `(whatsapp_account, template_id, metric_date, product_type)`.
- Daily pruning via `prune_old_marketing_metrics()` deletes records older than `MM_METRICS_RETENTION_DAYS` (90 days).
