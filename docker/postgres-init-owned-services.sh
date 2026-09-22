#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v credential_db_name="$CREDENTIAL_DB_NAME" \
  -v credential_db_user="$CREDENTIAL_DB_USER" \
  -v credential_db_password="$CREDENTIAL_DB_PASSWORD" \
  -v rules_db_name="$RULES_DB_NAME" \
  -v rules_db_user="$RULES_DB_USER" \
  -v rules_db_password="$RULES_DB_PASSWORD" <<'EOSQL'
CREATE USER :"credential_db_user" WITH PASSWORD :'credential_db_password';
CREATE DATABASE :"credential_db_name" OWNER :"credential_db_user";
CREATE USER :"rules_db_user" WITH PASSWORD :'rules_db_password';
CREATE DATABASE :"rules_db_name" OWNER :"rules_db_user";
EOSQL
