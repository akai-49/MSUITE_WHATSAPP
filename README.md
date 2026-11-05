### MSuite WhatsApp

WhatsApp Business for MSuite: numbers, templates, lists, broadcasts, flows, calling and analytics.

#### Analytics Compaction & Storage Model
- **WhatsApp Analytics Snapshot Compaction**: `_save_snapshot` upserts exactly 1 row per `(whatsapp_account, metric_type, granularity)` using deterministic `snapshot_key = make_key(whatsapp_account, metric_type, granularity)` to prevent table bloat.
- **Deduplication Patch**: `whatsapp_compact_analytics_snapshots` deduplicates legacy rows, backfills `snapshot_key`, and adds a database unique constraint.
- **Marketing Messages Retention**: Prunes records older than `MM_METRICS_RETENTION_DAYS` (90 days).
- **Overview Dashboard Metrics (`get_dashboard_metrics`)**:
  - Period filtering (`7d`, `month` / month-to-date, `qtr` / 90 days) with previous-period comparison deltas.
  - Category rollup (`Marketing`, `Utility`, `Authentication`) aggregating sent, delivered, and read counts from `Channel Message` and `WhatsApp Templates`.
  - Account standing reporting real Meta sender quality rating (`High`, `Medium`, `Low`), messaging tier (`TIER_10K`, etc.), and template approval counts (`Approved`, `Pending`, `Rejected`).
  - Derived reply rate query in `analytics_query.py` measuring distinct contacts with an inbound `Channel Message` after an outbound one in the selected period (also feeding `conversations_opened`).
  - Pure rule-based Aivo helper (`services/analytics/aivo_facts.py`) reporting template rejections with reasons, quality rating alerts, and lowest delivery categories.
  - Preserves BUG-023 per-doctype permission gating and all legacy keys (`metrics`, `recent_templates`, `recent_broadcasts`).

#### Channels & Account Connect
- **WhatsApp Sticker & Local Media Upload**:
  - Full outbound `sticker` media kind support in `inbox_channel`, enforcing `WHATSAPP_STICKER_MIME` (`image/webp`) and omitting captions per Meta API requirements.
  - Automatic `_upload_local_media` pre-send processing: swaps site-hosted file links (`/files/`, `/private/files/`) for Meta media IDs with path traversal protection and `File` read permission enforcement.
- **Avatar Enqueue Delegation**:
  - `_handle_whatsapp_credentials` enqueues account avatar downloads lazily through `msuite_account_avatar_handler` hooks or dynamic import of `msuite_social.social_post.avatar.enqueue_account_avatar` to avoid a hard dependency on `msuite_social`.


### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch dev
bench install-app msuite_whatsapp
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/msuite_whatsapp
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
