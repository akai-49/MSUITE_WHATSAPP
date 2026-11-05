### MSuite WhatsApp

WhatsApp Business for MSuite: numbers, templates, lists, broadcasts, flows, calling and analytics.

#### Analytics Compaction & Storage Model
- **WhatsApp Analytics Snapshot Compaction**: `_save_snapshot` upserts exactly 1 row per `(whatsapp_account, metric_type, granularity)` using deterministic `snapshot_key = make_key(whatsapp_account, metric_type, granularity)` to prevent table bloat.
- **Deduplication Patch**: `whatsapp_compact_analytics_snapshots` deduplicates legacy rows, backfills `snapshot_key`, and adds a database unique constraint.
- **Marketing Messages Retention**: Prunes records older than `MM_METRICS_RETENTION_DAYS` (90 days).

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
