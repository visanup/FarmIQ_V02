-- Local shadow event store/outbox; not consumed by the production sync forwarder.
CREATE TABLE IF NOT EXISTS allocation_shadow_events (
    event_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    session_id TEXT,
    capture_id TEXT,
    model_version TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'weighvision.group_allocation.completed',
    schema_version TEXT NOT NULL DEFAULT '1.0',
    payload_json JSONB NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'held_shadow' CHECK (delivery_status = 'held_shadow'),
    shadow_only BOOLEAN NOT NULL DEFAULT TRUE CHECK (shadow_only),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS allocation_shadow_events_session_idx
ON allocation_shadow_events(tenant_id, session_id, capture_id, created_at);
CREATE TABLE IF NOT EXISTS session_bird_allocations (
    event_id UUID NOT NULL REFERENCES allocation_shadow_events(event_id),
    tenant_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    detection_index INTEGER NOT NULL CHECK (detection_index >= 0),
    model_version TEXT NOT NULL,
    raw_score_g DOUBLE PRECISION NOT NULL CHECK (raw_score_g > 0 AND raw_score_g < 'Infinity'::float8),
    allocated_weight_g DOUBLE PRECISION NOT NULL CHECK (allocated_weight_g > 0 AND allocated_weight_g < 'Infinity'::float8),
    prediction_status TEXT NOT NULL DEFAULT 'WEAK_ALLOCATION' CHECK (prediction_status = 'WEAK_ALLOCATION'),
    individual_accuracy_validated BOOLEAN NOT NULL DEFAULT FALSE CHECK (NOT individual_accuracy_validated),
    shadow_only BOOLEAN NOT NULL DEFAULT TRUE CHECK (shadow_only),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, detection_index)
);
CREATE INDEX IF NOT EXISTS session_bird_allocations_session_idx
ON session_bird_allocations(tenant_id, session_id, capture_id, model_version);
