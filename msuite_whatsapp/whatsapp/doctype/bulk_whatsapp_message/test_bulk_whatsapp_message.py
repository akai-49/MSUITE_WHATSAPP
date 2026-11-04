# Copyright (c) 2025, Shridhar Patil and Contributors
# See license.txt

import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from msuite_whatsapp.services.validators.bulk_message_validator import validate_carousel_configuration

# Cuts the auto test-record dependency walk at Bulk WhatsApp Message's
# own Link fields — CRM Organization and Item (via product_ids) both
# pull in erpnext's whole accounts/sales chain (down to `Payment
# Gateway`, which this bench's `payments` app doesn't have installed),
# and neither is needed: every test below builds its own minimal
# fixtures.
EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = ["CRM Organization", "Item"]


class TestBulkWhatsAppMessage(IntegrationTestCase):
    """Tests for Bulk WhatsApp Message doctype."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._ensure_test_account()
        cls._ensure_test_template()
        cls._ensure_test_inbox()
        cls._purge_test_channel_data()

    @classmethod
    def _purge_test_channel_data(cls):
        # See tearDown's comment — a run interrupted before tearDown (or
        # any pre-existing leftover) would otherwise get silently deduped
        # by the outbound dispatcher on the very next run.
        handle_names = frappe.get_all(
            "Channel Handle", filters={"platform_handle": ["in", cls._TEST_PHONES]}, pluck="name"
        )
        if handle_names:
            frappe.db.delete("Channel Message", {"channel_handle": ["in", handle_names]})
            frappe.db.delete("Conversation", {"channel_handle": ["in", handle_names]})
            frappe.db.delete("Channel Handle", {"name": ["in", handle_names]})
            frappe.db.commit()

    @classmethod
    def _ensure_test_inbox(cls):
        # send_to_phone -> send_message resolves an Active Inbox for the
        # channel (inbox/services/outbound.py::_default_inbox_for_channel)
        # before it will send anything — without one it throws
        # "No active Inbox configured for channel 'WhatsApp'".
        if not frappe.db.exists("Inbox", {"channel_type": "WhatsApp", "status": "Active"}):
            frappe.get_doc({
                "doctype": "Inbox",
                "inbox_name": "Test Bulk WA Inbox",
                "channel_type": "WhatsApp",
                "status": "Active",
            }).insert(ignore_permissions=True)
            frappe.db.commit()

    @classmethod
    def _ensure_test_account(cls):
        if not frappe.db.exists("WhatsApp Account", "Test WA Bulk Account"):
            account = frappe.get_doc({
                "doctype": "WhatsApp Account",
                "account_name": "Test WA Bulk Account",
                "status": "Active",
                "business_id": "bulk_test_business_id",
                "app_id": "bulk_test_app_id",
                "phones": [{
                    "phone_number_id": "bulk_test_phone_id",
                    "display_phone_number": "+1 bulk",
                    "status": "Active",
                    "is_default_incoming": 1,
                    "is_default_outgoing": 1,
                }],
            })
            account.insert(ignore_permissions=True)
            from frappe.utils.password import set_encrypted_password
            set_encrypted_password("WhatsApp Account", account.name, "test_bulk_token", "token")
            frappe.db.commit()

    @classmethod
    def _ensure_test_template(cls):
        template_name = "test_bulk_template-en"
        if not frappe.db.exists("WhatsApp Templates", template_name):
            doc = frappe.get_doc({
                "doctype": "WhatsApp Templates",
                "template_name": "test_bulk_template",
                "actual_name": "test_bulk_template",
                "template": "Hello {{1}}, your bulk message",
                "sample_values": "User",
                "category": "MARKETING",
                "language": frappe.db.get_value("Language", {"language_code": "en"}) or "en",
                "language_code": "en",
                "whatsapp_account": "Test WA Bulk Account",
                "status": "APPROVED",
                "id": "test_bulk_template_id",
            })
            doc.db_insert()
            frappe.db.commit()

    def setUp(self):
        # Set password within each test's transaction scope
        from frappe.utils.password import set_encrypted_password
        set_encrypted_password("WhatsApp Account", "Test WA Bulk Account", "test_bulk_token", "token")
        # Clear ALL defaults then set ours (db.set_value bypasses on_update hooks)
        frappe.db.sql("UPDATE `tabWhatsApp Phone Number` SET is_default_outgoing=0, is_default_incoming=0")
        frappe.db.sql(
            "UPDATE `tabWhatsApp Phone Number` SET is_default_outgoing=1, is_default_incoming=1 WHERE parent=%s",
            "Test WA Bulk Account",
        )


    _TEST_PHONES = ("919900112233", "919900112244", "919900112255", "919900112266")

    def tearDown(self):
        for name in frappe.get_all("Bulk WhatsApp Message", filters={"title": ["like", "Test Bulk%"]}, pluck="name"):
            frappe.db.set_value("Bulk WhatsApp Message", name, "docstatus", 2)
            frappe.delete_doc("Bulk WhatsApp Message", name, force=True)
        # The outbound dispatcher dedupes identical messages to the same
        # Conversation (see dispatcher.handle -> {"deduped": True}), so a
        # leftover Channel Message from a previous run silently swallows
        # this run's send with no error. Purge the full chain (message ->
        # conversation -> handle) for the fixed test phones so every run
        # starts clean.
        handle_names = frappe.get_all(
            "Channel Handle", filters={"platform_handle": ["in", self._TEST_PHONES]}, pluck="name"
        )
        if handle_names:
            frappe.db.delete("Channel Message", {"channel_handle": ["in", handle_names]})
            frappe.db.delete("Conversation", {"channel_handle": ["in", handle_names]})
            frappe.db.delete("Channel Handle", {"name": ["in", handle_names]})
        frappe.db.commit()

    def _make_bulk_message(self, **kwargs):
        """Helper to create a Bulk WhatsApp Message."""
        doc = frappe.get_doc({
            "doctype": "Bulk WhatsApp Message",
            "title": kwargs.get("title", "Test Bulk Message 1"),
            "recipient_type": kwargs.get("recipient_type", "Individual"),
            "use_template": kwargs.get("use_template", 1),
            "template": kwargs.get("template", "test_bulk_template-en"),
            "variable_type": kwargs.get("variable_type", "Common"),
            "whatsapp_account": kwargs.get("whatsapp_account", "Test WA Bulk Account"),
        })
        recipients = kwargs.get("recipients", [
            {"mobile_number": "919900112233", "recipient_name": "User 1"},
            {"mobile_number": "919900112244", "recipient_name": "User 2"},
        ])
        for r in recipients:
            doc.append("recipients", r)
        doc.insert(ignore_permissions=True)
        return doc

    def test_bulk_message_creation(self):
        """Test basic bulk message creation."""
        doc = self._make_bulk_message()
        self.assertTrue(frappe.db.exists("Bulk WhatsApp Message", doc.name))
        self.assertEqual(doc.status, "Draft")

    def test_autoname_format(self):
        """Test bulk message autoname starts with BULK-WA-."""
        doc = self._make_bulk_message(title="Test Bulk Autoname")
        self.assertTrue(doc.name.startswith("BULK-WA-"))

    def test_validate_recipients_required(self):
        """Test that at least one recipient or list is required."""
        with self.assertRaises(frappe.ValidationError):
            doc = frappe.get_doc({
                "doctype": "Bulk WhatsApp Message",
                "title": "Test Bulk No Recipients",
                "recipient_type": "Individual",
                "use_template": 1,
                "template": "test_bulk_template-en",
                "whatsapp_account": "Test WA Bulk Account",
            })
            # No recipients added
            doc.insert(ignore_permissions=True)

    def test_recipient_count_set_on_validate(self):
        """Test that recipient_count is set during validation."""
        doc = self._make_bulk_message(title="Test Bulk Count")
        self.assertEqual(doc.recipient_count, 2)

    @patch("msuite_whatsapp.services.channels.inbox_channel.send_to_meta")
    def test_on_submit_queues_messages(self, mock_post):
        """Test that submitting queues the messages."""
        mock_post.return_value = ({
            "messages": [{"id": "wamid.bulk_test_1"}],
        }, "cloud_api")
        doc = self._make_bulk_message(title="Test Bulk Submit")
        doc.submit()
        doc.reload()
        self.assertEqual(doc.status, "Queued")

    @patch("msuite_whatsapp.services.channels.inbox_channel.send_to_meta")
    def test_create_single_message(self, mock_post):
        """Test creating a single message from bulk."""
        # `WhatsApp Message` was migrated to `Channel Message` (see
        # patches/migrate_whatsapp_message_to_channel_message.py) — the
        # recipient's phone now lives on the linked `Channel Handle`,
        # not directly on the message row.
        mock_post.return_value = ({
            "messages": [{"id": "wamid.bulk_single_1"}],
        }, "cloud_api")
        doc = self._make_bulk_message(title="Test Bulk Single")

        recipient = {
            "mobile_number": "919900112255",
            "recipient_name": "Single Test",
            "recipient_data": json.dumps({"name": "Single Test"}),
        }
        doc.create_single_message(recipient)

        handle = frappe.db.get_value(
            "Channel Handle", {"platform_handle": "919900112255"}, "name"
        )
        self.assertTrue(handle)
        self.assertTrue(
            frappe.db.exists(
                "Channel Message",
                {"channel_handle": handle, "reference_doctype": doc.doctype, "reference_name": doc.name},
            )
        )

    def test_get_progress(self):
        """Test get_progress returns correct structure."""
        doc = self._make_bulk_message(title="Test Bulk Progress")
        progress = doc.get_progress()
        self.assertIn("total", progress)
        self.assertIn("sent", progress)
        self.assertIn("failed", progress)
        self.assertIn("queued", progress)
        self.assertIn("percent", progress)
        self.assertEqual(progress["total"], 2)

    @patch("msuite_whatsapp.services.channels.inbox_channel.send_to_meta")
    def test_retry_failed(self, mock_post):
        """Test retry_failed requeues failed messages."""
        # `WhatsApp Message` was migrated to `Channel Message`. Per
        # bulk_send_service.retry_failed's own docstring, the OLD failed
        # Channel Message row is left as history — retry re-sends through
        # a brand-new Channel Message and flips the WhatsApp Recipient row
        # (not the old failed row) back to Queued. Also: retry_failed only
        # re-sends recipients that are already in doc.recipients, so the
        # failed phone must be one of the two default recipients.
        mock_post.return_value = ({
            "messages": [{"id": "wamid.bulk_retry_1"}],
        }, "cloud_api")

        doc = self._make_bulk_message(title="Test Bulk Retry")
        failed_phone = "919900112233"

        # Send once for real (through the mocked post_to_meta) so the
        # Conversation/Inbox/Channel Handle it needs get created the
        # normal way, then flip the resulting Channel Message to
        # "failed" — the shape retry_failed actually queries.
        doc.create_single_message(
            {"mobile_number": failed_phone, "recipient_name": "User 1", "recipient_data": "{}"}
        )
        msg_name = frappe.db.get_value(
            "Channel Message",
            {"reference_doctype": doc.doctype, "reference_name": doc.name},
            "name",
        )
        self.assertTrue(msg_name)
        frappe.db.set_value("Channel Message", msg_name, "status", "failed")
        frappe.db.commit()

        doc.retry_failed()

        recipient_status = frappe.db.get_value(
            "WhatsApp Recipient",
            {"parent": doc.name, "parenttype": "Bulk WhatsApp Message", "mobile_number": failed_phone},
            "status",
        )
        self.assertEqual(recipient_status, "Queued")

    @patch("msuite_campaigns.aws_pipeline.dispatch.export_and_enqueue")
    @patch("msuite_campaigns.aws_pipeline.dispatch.should_use_aws", return_value=True)
    def test_queue_messages_aws_excludes_optedout_and_sent(self, mock_should_use_aws, mock_export_and_enqueue):
        """The exact bug: `queue_messages` used to flip every recipient row
        to Queued with a raw SQL UPDATE before the AWS/Standard decision, so
        an AWS-routed blast re-derived rows from the DB and force-included
        duplicates and opted-out numbers. Dedupe/suppression must happen
        before the flip and before the AWS manifest is built, same as SMS
        and Email."""
        from msuite_whatsapp.services.bulk import bulk_send_service

        sendable_phone = "919900112233"
        already_sent_phone = "919900112244"
        opted_out_phone = "919900112255"

        doc = self._make_bulk_message(
            title="Test Bulk AWS Suppression",
            recipients=[
                {"mobile_number": sendable_phone, "recipient_name": "Sendable"},
                {"mobile_number": already_sent_phone, "recipient_name": "Already Sent"},
                {"mobile_number": opted_out_phone, "recipient_name": "Opted Out"},
            ],
        )

        # Mark one recipient row as already sent -- must be excluded like a
        # duplicate/attempted recipient.
        frappe.db.set_value(
            "WhatsApp Recipient",
            {"parent": doc.name, "parenttype": "Bulk WhatsApp Message", "mobile_number": already_sent_phone},
            "status",
            "Sent",
        )

        # Mark another recipient as opted out of WhatsApp via Audience Member
        # -- WhatsApp's own opt-out concept (`unsubscribed_whatsapp`).
        audience = frappe.get_doc({
            "doctype": "Audience", "audience_name": "ZZTest WA OptOut", "default_region": "IN"
        })
        audience.flags.ignore_permissions = True
        audience.insert()
        audience.append("members", {
            "full_name": "Opted Out", "raw_phone": opted_out_phone,
            "phone_e164": opted_out_phone, "phone_status": "Valid",
            "phone_type": "Mobile", "unsubscribed_whatsapp": 1,
        })
        audience.save()
        self.addCleanup(
            lambda: frappe.delete_doc("Audience", audience.name, force=True, ignore_permissions=True)
        )

        self.assertTrue(bulk_send_service.is_opted_out(opted_out_phone))

        bulk_send_service.queue_messages(doc)

        # Routed via AWS (mocked): the manifest input must contain only the
        # one sendable recipient.
        mock_export_and_enqueue.assert_called_once()
        called_doc, called_rows = mock_export_and_enqueue.call_args[0]
        self.assertEqual(called_doc.name, doc.name)
        self.assertEqual(len(called_rows), 1)
        self.assertEqual(called_rows[0]["mobile_number"], sendable_phone)

        # Neither excluded row was flipped to Queued by the pre-AWS-decision
        # raw SQL flip this fix removes.
        already_sent_status = frappe.db.get_value(
            "WhatsApp Recipient",
            {"parent": doc.name, "parenttype": "Bulk WhatsApp Message", "mobile_number": already_sent_phone},
            "status",
        )
        opted_out_status = frappe.db.get_value(
            "WhatsApp Recipient",
            {"parent": doc.name, "parenttype": "Bulk WhatsApp Message", "mobile_number": opted_out_phone},
            "status",
        )
        self.assertEqual(already_sent_status, "Sent")
        self.assertEqual(opted_out_status, "Unsubscribed")

    @patch("msuite_whatsapp.services.channels.inbox_channel.send_to_meta")
    def test_optedout_row_survives_batched_enqueue_rederivation(self, mock_post):
        """`dispatch/batched_enqueue.py`'s chunk path re-derives its own
        sendable set straight from each row's `status` column
        (`SENDABLE_STATUSES = ("Queued", "Retrying")`), completely
        independent of `queue_messages`'s `to_send` list. If `queue_messages`
        only skipped an opted-out row without changing its status, a row
        that happened to already be "Queued" (e.g. from an earlier partial
        run, before the recipient opted out) would still be picked up and
        resent by a batched-enqueue blast. `queue_messages` must stamp
        opted-out rows "Unsubscribed" so they fall out of every
        sendable-status filter, not just its own."""
        from msuite_campaigns.dispatch.batched_enqueue import _slice_recipients
        from msuite_whatsapp.services.bulk import bulk_send_service

        mock_post.return_value = ({"messages": [{"id": "wamid.bulk_batched_1"}]}, "cloud_api")

        opted_out_phone = "919900112266"
        doc = self._make_bulk_message(
            title="Test Bulk Batched OptOut",
            recipients=[
                {"mobile_number": "919900112233", "recipient_name": "Sendable"},
                {"mobile_number": opted_out_phone, "recipient_name": "Opted Out"},
            ],
        )

        optout_row_name = frappe.db.get_value(
            "WhatsApp Recipient",
            {"parent": doc.name, "parenttype": "Bulk WhatsApp Message", "mobile_number": opted_out_phone},
            "name",
        )
        # Simulate the exact risk this closes: the row was already Queued
        # by the time the recipient opted out.
        frappe.db.set_value("WhatsApp Recipient", optout_row_name, "status", "Queued")

        audience = frappe.get_doc({
            "doctype": "Audience", "audience_name": "ZZTest WA Batched OptOut", "default_region": "IN"
        })
        audience.flags.ignore_permissions = True
        audience.insert()
        audience.append("members", {
            "full_name": "Opted Out", "raw_phone": opted_out_phone,
            "phone_e164": opted_out_phone, "phone_status": "Valid",
            "phone_type": "Mobile", "unsubscribed_whatsapp": 1,
        })
        audience.save()
        self.addCleanup(
            lambda: frappe.delete_doc("Audience", audience.name, force=True, ignore_permissions=True)
        )

        # Test mode routes Standard by default (aws_pipeline.dispatch.is_ready
        # returns False under frappe.flags.in_test without the force-ready
        # flag) -- no AWS mocking needed to exercise the flip/stamp path.
        bulk_send_service.queue_messages(doc)

        row_status = frappe.db.get_value("WhatsApp Recipient", optout_row_name, "status")
        self.assertEqual(row_status, "Unsubscribed")

        max_idx = frappe.db.count(
            "WhatsApp Recipient", {"parent": doc.name, "parenttype": "Bulk WhatsApp Message"}
        )
        sliced = _slice_recipients("Bulk WhatsApp Message", doc.name, 1, max_idx)
        sliced_names = {r["name"] for r in sliced}
        self.assertNotIn(optout_row_name, sliced_names)

    @patch("frappe.enqueue_doc")
    def test_second_blast_reuses_shared_recipient_list(self, mock_enqueue):
        """WhatsApp Recipient List rows are SHARED across blasts (unlike
        SMS/Email, whose recipient rows are always freshly created per
        blast), so their `status` column carries the PREVIOUS blast's
        outcome. Filtering on it made a second blast to the same saved list
        compute `to_send == []` and silently no-op — zero messages, zero
        errors, doc stuck forever. A list-backed blast must decide
        "already attempted" per-blast off Channel Message instead, while
        still suppressing opt-outs, and must still settle to a terminal
        status even though the excluded row never produces a Channel
        Message.

        Since audit H11 the blast snapshots the list into its OWN rows on
        first queue, so every status below is read off the blast's rows and
        the shared list rows must stay untouched."""
        from msuite_whatsapp.services.bulk import bulk_send_service

        resent_phone = "919900112233"     # already Sent by the first blast
        pending_phone = "919900112244"    # never attempted
        opted_out_phone = "919900112255"

        rec_list = frappe.get_doc({
            "doctype": "WhatsApp Recipient List",
            "list_name": "Test Shared Bulk List",
        })
        for phone, label in (
            (resent_phone, "Already Sent"),
            (pending_phone, "Pending"),
            (opted_out_phone, "Opted Out"),
        ):
            rec_list.append("recipients", {"mobile_number": phone, "recipient_name": label})
        rec_list.insert(ignore_permissions=True)
        self.addCleanup(
            lambda: frappe.delete_doc("WhatsApp Recipient List", rec_list.name, force=True)
        )

        def row_of(phone):
            return frappe.db.get_value(
                "WhatsApp Recipient",
                {"parent": rec_list.name, "parenttype": "WhatsApp Recipient List", "mobile_number": phone},
                "name",
            )

        def own_row_of(phone):
            return frappe.db.get_value(
                "WhatsApp Recipient",
                {"parent": doc.name, "parenttype": "Bulk WhatsApp Message", "mobile_number": phone},
                "name",
            )

        # The first blast already delivered to one of them — this is the
        # state that used to make the second blast compute to_send == [].
        frappe.db.set_value("WhatsApp Recipient", row_of(resent_phone), "status", "Sent")

        audience = frappe.get_doc({
            "doctype": "Audience", "audience_name": "ZZTest WA Shared List OptOut", "default_region": "IN"
        })
        audience.flags.ignore_permissions = True
        audience.insert()
        audience.append("members", {
            "full_name": "Opted Out", "raw_phone": opted_out_phone,
            "phone_e164": opted_out_phone, "phone_status": "Valid",
            "phone_type": "Mobile", "unsubscribed_whatsapp": 1,
        })
        audience.save()
        self.addCleanup(
            lambda: frappe.delete_doc("Audience", audience.name, force=True, ignore_permissions=True)
        )

        doc = frappe.get_doc({
            "doctype": "Bulk WhatsApp Message",
            "title": "Test Bulk Second Blast",
            "delivery_engine": "Standard",
            "recipient_type": "Recipient List",
            "recipient_list": rec_list.name,
            "use_template": 1,
            "template": "test_bulk_template-en",
            "variable_type": "Common",
            "whatsapp_account": "Test WA Bulk Account",
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.recipient_count, 3)

        mock_enqueue.reset_mock()  # ignore anything insert-time hooks enqueued
        bulk_send_service.queue_messages(doc)

        # Critical: the already-Sent row is re-sent by this NEW blast, and
        # the never-attempted row goes out too. Previously: nothing at all.
        enqueued = {
            call.kwargs["recipient"]["mobile_number"] for call in mock_enqueue.call_args_list
        }
        self.assertEqual(enqueued, {resent_phone, pending_phone})
        self.assertEqual(frappe.db.get_value("WhatsApp Recipient", own_row_of(resent_phone), "status"), "Queued")
        self.assertEqual(frappe.db.get_value("WhatsApp Recipient", own_row_of(pending_phone), "status"), "Queued")

        # Task 2's whole point still holds: the opted-out number is excluded.
        self.assertEqual(
            frappe.db.get_value("WhatsApp Recipient", own_row_of(opted_out_phone), "status"), "Unsubscribed"
        )

        # Audit H11: the shared list is never written by a send.
        self.assertEqual(frappe.db.get_value("WhatsApp Recipient", row_of(resent_phone), "status"), "Sent")
        self.assertIn(frappe.db.get_value("WhatsApp Recipient", row_of(pending_phone), "status"), ("", None))
        self.assertIn(frappe.db.get_value("WhatsApp Recipient", row_of(opted_out_phone), "status"), ("", None))

        # Important: the blast settles once nothing is outstanding, even
        # though only 2 of its 3 recipients could ever be attempted (the
        # old Channel-Message-count >= recipient_count test never could).
        for phone in (resent_phone, pending_phone):
            frappe.db.set_value("WhatsApp Recipient", own_row_of(phone), "status", "Sent")
        bulk_send_service._check_and_update_completion(doc)
        self.assertEqual(
            frappe.db.get_value("Bulk WhatsApp Message", doc.name, "status"), "Completed"
        )

        # Important: re-subscribing un-excludes the member. The stamp on the
        # SHARED list row must never outlive the live opt-out flag.
        frappe.db.set_value(
            "Audience Member",
            {"parent": audience.name, "phone_e164": opted_out_phone},
            "unsubscribed_whatsapp",
            0,
        )
        self.assertFalse(bulk_send_service.is_opted_out(opted_out_phone))

        mock_enqueue.reset_mock()
        bulk_send_service.queue_messages(doc)
        re_enqueued = {
            call.kwargs["recipient"]["mobile_number"] for call in mock_enqueue.call_args_list
        }
        self.assertIn(opted_out_phone, re_enqueued)
        self.assertEqual(
            frappe.db.get_value("WhatsApp Recipient", own_row_of(opted_out_phone), "status"), "Queued"
        )

    def test_progress_percent_agrees_with_pending_when_a_row_is_unsubscribed(self):
        """`pending` excludes permanently-excluded (Unsubscribed) rows from
        the outstanding count, so `percent` has to divide by the same
        excluded-aware denominator. Dividing by the raw recipient total made
        a blast with one opt-out report `pending: 0` (nothing left to do)
        next to `percent: 50` (looks half finished) on the same payload."""
        from msuite_whatsapp.services.bulk import bulk_send_service

        sent_phone = "919900117001"
        opted_out_phone = "919900117002"
        doc = self._make_bulk_message(
            title="Test Bulk Progress Percent",
            recipients=[
                {"mobile_number": sent_phone, "recipient_name": "Sent"},
                {"mobile_number": opted_out_phone, "recipient_name": "Opted Out"},
            ],
        )

        for phone, status in ((sent_phone, "Sent"), (opted_out_phone, "Unsubscribed")):
            frappe.db.set_value(
                "WhatsApp Recipient",
                {
                    "parent": doc.name,
                    "parenttype": "Bulk WhatsApp Message",
                    "mobile_number": phone,
                },
                "status",
                status,
            )

        progress = bulk_send_service.get_progress(doc)
        self.assertEqual(progress["unsubscribed"], 1)
        self.assertEqual(progress["pending"], 0)
        self.assertEqual(progress["percent"], 100)

    @patch("frappe.enqueue")
    def test_batched_enqueue_finds_shared_recipient_list_rows(self, mock_enqueue):
        """`dispatch/batched_enqueue.py` filtered recipient rows by
        `parent = <blast name>`. For a WhatsApp "Recipient List" blast the
        rows live under the SHARED `WhatsApp Recipient List`, so a
        `use_batched_enqueue=1` blast on a saved list matched zero rows:
        no chunk jobs, no sends, no error anywhere. Parent has to be
        resolved per channel, the same way `_row_parent` /
        `aws_pipeline/manifest.py::row_parent` already do."""
        from msuite_campaigns.dispatch import batched_enqueue
        from msuite_whatsapp.services.bulk import bulk_send_service

        phones = ("919900118001", "919900118002")
        rec_list = frappe.get_doc({
            "doctype": "WhatsApp Recipient List",
            "list_name": "Test Batched Shared List",
        })
        for i, phone in enumerate(phones):
            rec_list.append("recipients", {"mobile_number": phone, "recipient_name": f"Batched {i}"})
        rec_list.insert(ignore_permissions=True)
        self.addCleanup(
            lambda: frappe.delete_doc("WhatsApp Recipient List", rec_list.name, force=True)
        )

        doc = frappe.get_doc({
            "doctype": "Bulk WhatsApp Message",
            "title": "Test Bulk Batched List",
            "recipient_type": "Recipient List",
            "recipient_list": rec_list.name,
            "use_template": 1,
            "template": "test_bulk_template-en",
            "variable_type": "Common",
            "whatsapp_account": "Test WA Bulk Account",
        })
        doc.insert(ignore_permissions=True)
        doc.db_set("use_batched_enqueue", 1)
        doc.reload()

        mock_enqueue.reset_mock()
        bulk_send_service.queue_messages(doc)

        # 2 recipients, chunk size 500 -> exactly one chunk job. Before the
        # fix: zero, because max(idx) over `parent = doc.name` was NULL.
        self.assertEqual(mock_enqueue.call_count, 1)
        self.assertIn("run_chunk", mock_enqueue.call_args.args[0])

        # And the chunk itself must actually see both rows.
        sliced = batched_enqueue._slice_recipients(
            "Bulk WhatsApp Message",
            doc.name,
            mock_enqueue.call_args.kwargs["start_idx"],
            mock_enqueue.call_args.kwargs["end_idx"],
        )
        self.assertEqual({r["mobile_number"] for r in sliced}, set(phones))

    def test_submit_rejects_unapproved_template(self):
        """A template that Meta hasn't approved must block submit — without
        this the blast queues fine and every recipient fails individually
        at send time instead."""
        doc = self._make_bulk_message(title="Test Bulk Unapproved Template")
        # Flip the template to a non-approved status after insert (insert
        # itself validated fine against the APPROVED fixture template) so
        # the check is proven to fire again on submit, not just on insert.
        frappe.db.set_value("WhatsApp Templates", "test_bulk_template-en", "status", "REJECTED")
        frappe.db.commit()
        self.addCleanup(
            lambda: frappe.db.set_value(
                "WhatsApp Templates", "test_bulk_template-en", "status", "APPROVED"
            )
        )
        with self.assertRaises(frappe.ValidationError):
            doc.submit()

    def test_validate_with_recipient_list(self):
        """Test validation with recipient_list type."""
        # Create a recipient list first
        rec_list = frappe.get_doc({
            "doctype": "WhatsApp Recipient List",
            "list_name": "Test Recipient Bulk List",
        })
        rec_list.append("recipients", {"mobile_number": "919900112277", "recipient_name": "List User"})
        rec_list.insert(ignore_permissions=True)

        doc = frappe.get_doc({
            "doctype": "Bulk WhatsApp Message",
            "title": "Test Bulk With List",
            "recipient_type": "Recipient List",
            "recipient_list": rec_list.name,
            "use_template": 1,
            "template": "test_bulk_template-en",
            "whatsapp_account": "Test WA Bulk Account",
        })
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.recipient_count, 1)

        # Cleanup
        frappe.delete_doc("WhatsApp Recipient List", rec_list.name, force=True)


def _carousel_doc(is_carousel_template=1, carousel_catalog="CAT-1", item_codes=None, template=None):
    item_codes = item_codes if item_codes is not None else ["ITEM-1", "ITEM-2"]
    return SimpleNamespace(
        is_carousel_template=is_carousel_template,
        template=template,
        carousel_catalog=carousel_catalog,
        product_ids=[SimpleNamespace(item_code=code) for code in item_codes],
    )


class TestValidateCarouselConfiguration(IntegrationTestCase):
    """validate_carousel_configuration now also looks up the doc's own
    `template`'s carousel cards (_is_product_carousel queries WhatsApp
    Template Carousel Card by parent) to tell a Product Card Carousel
    from a Media Card Carousel — no longer a pure function, so this
    needs a real WhatsApp Templates fixture with a PRODUCT header card,
    not a bare SimpleNamespace."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template_name = "test_carousel_validator_template-en"
        if not frappe.db.exists("WhatsApp Templates", cls.template_name):
            doc = frappe.get_doc({
                "doctype": "WhatsApp Templates",
                "template_name": "test_carousel_validator_template",
                "actual_name": "test_carousel_validator_template",
                "template": "Carousel template",
                "category": "MARKETING",
                "language": frappe.db.get_value("Language", {"language_code": "en"}) or "en",
                "language_code": "en",
                "status": "APPROVED",
                "id": "test_carousel_validator_template_id",
                "carousel_cards": [{"card_index": 0, "header_format": "PRODUCT"}],
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()

    def test_skips_when_not_carousel_template(self):
        validate_carousel_configuration(_carousel_doc(is_carousel_template=0, carousel_catalog="", item_codes=[]))

    def test_passes_with_catalog_and_two_products(self):
        validate_carousel_configuration(_carousel_doc(template=self.template_name))

    def test_throws_without_catalog(self):
        with self.assertRaises(frappe.ValidationError):
            validate_carousel_configuration(_carousel_doc(carousel_catalog="", template=self.template_name))

    def test_throws_with_one_product(self):
        with self.assertRaises(frappe.ValidationError):
            validate_carousel_configuration(
                _carousel_doc(item_codes=["ITEM-1"], template=self.template_name)
            )

    def test_throws_with_eleven_products(self):
        with self.assertRaises(frappe.ValidationError):
            validate_carousel_configuration(
                _carousel_doc(item_codes=[f"ITEM-{i}" for i in range(11)], template=self.template_name)
            )


class TestInsertBulkMessageDraftUpdate(TestCase):
	"""BUG-021: Save Draft with a known draft name updates it in place."""

	def _call(self, existing, **kwargs):
		from msuite_whatsapp.api.v1.app import bulk_messages

		with (
			patch.object(bulk_messages, "check_write"),
			patch.object(bulk_messages, "check_create") as check_create,
			patch("frappe.get_doc", return_value=existing) as get_doc,
			patch("frappe.db.commit"),
		):
			bulk_messages.insert_bulk_message(json.dumps({"title": "June update"}), **kwargs)
		return get_doc, check_create

	def test_named_draft_is_updated_not_inserted(self):
		from unittest.mock import MagicMock

		draft = MagicMock(docstatus=0)
		get_doc, check_create = self._call(draft, name="BWM-0001")

		get_doc.assert_called_once_with("Bulk WhatsApp Message", "BWM-0001")
		draft.update.assert_called_once()
		self.assertEqual(draft.update.call_args[0][0]["title"], "June update")
		draft.save.assert_called_once()
		draft.insert.assert_not_called()
		draft.submit.assert_not_called()
		check_create.assert_not_called()

	def test_sent_broadcast_cannot_be_overwritten(self):
		from unittest.mock import MagicMock

		sent = MagicMock(docstatus=1)
		with self.assertRaises(frappe.ValidationError):
			self._call(sent, name="BWM-0001")
		sent.save.assert_not_called()


class TestListBlastCompletion(TestCase):
	"""A Recipient List blast must not settle while list rows are still
	Queued/Retrying — it used to go Completed after the first send."""

	def _run(self, pending, sent=1, failed=0):
		from unittest.mock import MagicMock

		from msuite_whatsapp.services.bulk import bulk_send_service as svc

		doc = SimpleNamespace(
			doctype="Bulk WhatsApp Message", name="BWM-LIST", recipient_type="Recipient List",
			recipient_list="RL-1", sent_count=0,
		)

		def fake_count(doctype, filters=None, **kw):
			filters = filters or kw.get("filters") or {}
			if doctype == "WhatsApp Recipient":
				self.assertEqual((filters["parent"], filters["parenttype"]), ("RL-1", "WhatsApp Recipient List"))
				return pending
			return failed if filters.get("status") == "failed" else sent

		cache = MagicMock()
		cache.llen.return_value = 0
		with (
			patch.object(svc, "row_parent", return_value=("RL-1", "WhatsApp Recipient List")),
			patch("frappe.db.get_value", return_value="In Progress"),
			patch("frappe.db.count", side_effect=fake_count),
			patch("frappe.cache", return_value=cache),
			patch("frappe.db.sql") as sql,
		):
			svc._check_and_update_completion(doc)
		return sql

	def test_list_blast_with_queued_rows_stays_in_progress(self):
		self._run(pending=999).assert_not_called()

	def test_list_blast_settles_when_no_rows_pending(self):
		sql = self._run(pending=0, sent=5)
		sql.assert_called_once()
		self.assertEqual(sql.call_args[0][1][0], "Completed")
