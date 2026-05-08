-- PranaNew PostgreSQL database schema design
-- TASK-005: final DDL design before creating migrations.
-- TASK-006: initial one-time migration. Re-running on the same schema is not supported;
-- apply once to an empty database/schema, or rebuild the database before replaying.
--
-- Availability is calculated from booking_slots joined to bookings where
-- bookings.status is active or completed. Cancelled bookings free their slots.
-- Slots do not store a separate cached counter as the source of truth.

CREATE TABLE users (
    tg_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language TEXT NOT NULL DEFAULT 'ru' CHECK (language IN ('ru', 'en', 'sr')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE settings (
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (key)
);

CREATE TABLE slots (
    id BIGSERIAL PRIMARY KEY,
    slot_date DATE NOT NULL,
    starts_at TIME NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 10 CHECK (duration_minutes > 0),
    capacity INTEGER NOT NULL DEFAULT 1 CHECK (capacity > 0),
    is_blocked BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (slot_date, starts_at),
    UNIQUE (start_time)
);

CREATE TABLE bookings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(tg_id),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'cancelled')),
    customer_name TEXT,
    customer_phone TEXT,
    comment TEXT NOT NULL DEFAULT '',
    pickup_time TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    cancellation_reason TEXT
);

CREATE TABLE booking_slots (
    booking_id BIGINT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    slot_id BIGINT NOT NULL REFERENCES slots(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (booking_id, slot_id)
);

CREATE TABLE reviews (
    id BIGSERIAL PRIMARY KEY,
    booking_id BIGINT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(tg_id),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'published', 'rejected')),
    text TEXT NOT NULL,
    rating INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    moderated_at TIMESTAMPTZ,
    UNIQUE (booking_id)
);

CREATE TABLE i18n_texts (
    language TEXT NOT NULL CHECK (language IN ('ru', 'en', 'sr')),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (language, key)
);

-- Optional persisted jobs for review reminders and future scheduled notifications.
CREATE TABLE scheduler_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed', 'cancelled')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE analytics_events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('free_slots_view', 'booking_created', 'booking_cancelled', 'booking_completed')),
    user_id BIGINT REFERENCES users(tg_id),
    booking_id BIGINT REFERENCES bookings(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_slots_date_starts_at ON slots (slot_date, starts_at);
CREATE INDEX idx_slots_blocked_date ON slots (is_blocked, slot_date);
CREATE INDEX idx_booking_slots_slot_id ON booking_slots (slot_id);
CREATE INDEX idx_bookings_user_id_status ON bookings (user_id, status);
CREATE INDEX idx_bookings_status_created_at ON bookings (status, created_at);
CREATE INDEX idx_reviews_status_created_at ON reviews (status, created_at);
CREATE INDEX idx_scheduler_jobs_status_run_at ON scheduler_jobs (status, run_at);
CREATE INDEX idx_analytics_events_type_created_at ON analytics_events (event_type, created_at);
