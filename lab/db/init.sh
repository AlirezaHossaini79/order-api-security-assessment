#!/bin/sh
# Runs on a fresh volume; can also be rerun for an existing lab volume.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=admin_password="$(cat /run/secrets/db_admin_password)" \
  --set=app_password="$(cat /run/secrets/db_app_password)" <<'SQL'
SELECT format('ALTER ROLE %I PASSWORD %L', current_user, :'admin_password') \gexec
SELECT 'CREATE ROLE lab_app LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='lab_app') \gexec
ALTER ROLE lab_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE lab_app PASSWORD :'app_password';
REVOKE ALL ON DATABASE lab FROM PUBLIC;
GRANT CONNECT ON DATABASE lab TO lab_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO lab_app;
CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    owner TEXT NOT NULL,
    item TEXT NOT NULL,
    request_key TEXT NOT NULL
);
INSERT INTO orders(owner,item,request_key)
SELECT 'alice','seed-a','seed-a' WHERE NOT EXISTS (SELECT 1 FROM orders);
INSERT INTO orders(owner,item,request_key)
SELECT 'bob','seed-b','seed-b' WHERE NOT EXISTS (SELECT 1 FROM orders WHERE owner='bob');
REVOKE ALL ON orders FROM lab_app;
GRANT SELECT, INSERT ON orders TO lab_app;
GRANT USAGE, SELECT ON SEQUENCE orders_id_seq TO lab_app;
SQL
