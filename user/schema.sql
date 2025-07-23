CREATE TABLE IF NOT EXISTS users (
    uuid BINARY(16) PRIMARY KEY,
    auth0_sub VARCHAR(255) UNIQUE, -- Populated in Auth0 mode. The Auth0 user ID.
    email VARCHAR(255) UNIQUE,
    is_anonymous BOOLEAN DEFAULT FALSE, -- Used for the guest -> registered flow in Auth0 mode.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
); 