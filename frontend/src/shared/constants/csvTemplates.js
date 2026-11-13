/**
 * Downloadable CSV templates with single sample row.
 *
 * User ruling exception: downloadable CSV templates KEEP one sample row
 * (explicit user instruction overriding the no-sample-data rule).
 * Each template is kept as a single named constant, exempted by the guard test.
 */

/** Downloadable Customer Audience CSV template with header and single sample row. */
export const CUSTOMER_AUDIENCE_CSV_TEMPLATE =
  'EMAIL,PHONE,FN,LN,ZIP\nalice@example.com,+15551234567,Alice,Anderson,94105\n'

/** Downloadable WhatsApp Recipients CSV template with header and single sample row. */
export const WHATSAPP_RECIPIENTS_CSV_TEMPLATE =
  'mobile_number,recipient_name,company,city\n+919876543210,John Doe,Acme Corp,Mumbai\n'
