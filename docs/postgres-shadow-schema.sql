-- Target schema for real bank shadow data. Local SQLite remains synthetic-only.
CREATE TABLE partner_case (
  application_id uuid PRIMARY KEY,
  owner_actor text NOT NULL,
  business_type text NOT NULL,
  requested_mxn numeric(14,2) NOT NULL,
  raw_application_ciphertext bytea NOT NULL,
  raw_result_ciphertext bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE shadow_performance_event (
  event_id text PRIMARY KEY,
  application_id uuid NOT NULL REFERENCES partner_case(application_id),
  owner_actor text NOT NULL,
  period_end timestamptz NOT NULL,
  days_past_due integer NOT NULL CHECK (days_past_due >= 0),
  status text NOT NULL,
  outstanding_balance_mxn numeric(14,2) NOT NULL CHECK (outstanding_balance_mxn >= 0),
  payload_ciphertext bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE partner_case ENABLE ROW LEVEL SECURITY;
ALTER TABLE shadow_performance_event ENABLE ROW LEVEL SECURITY;
CREATE POLICY partner_case_tenant ON partner_case
  USING (owner_actor = current_setting('olin.actor', true));
CREATE POLICY performance_tenant ON shadow_performance_event
  USING (owner_actor = current_setting('olin.actor', true));

-- The deployment must use a managed encrypted service, TLS, KMS envelope
-- encryption for ciphertext columns, point-in-time recovery, and a tested
-- restore procedure. This file is a migration target, not proof of operation.
