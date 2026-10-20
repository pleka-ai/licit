-- Objects of the retired FastAPI/web stack (formerly 11_api, 12_auth and
-- 13_web_stats) and of the flat D1 export. Restored state dumps still carry
-- them, and their triggers would keep firing on every ETL insert, so drop them.
-- Idempotent.

DROP MATERIALIZED VIEW IF EXISTS mv_landing_stats;
DROP MATERIALIZED VIEW IF EXISTS mv_licitacion;
DROP VIEW IF EXISTS v_licitacion, v_criterio, v_solvencia, v_documento, v_lote, v_cpv,
  v_adjudicacion;

DROP TRIGGER IF EXISTS empresa_upsert_trigger ON winning_party;
DROP TRIGGER IF EXISTS cfs_search_trigger ON contract_folder_status;
DROP FUNCTION IF EXISTS empresa_upsert(), cfs_search_update(), refresh_mv_licitacion(),
  refresh_mv_landing_stats();
DROP TABLE IF EXISTS empresa, audit_log, api_key, api_user, d1_sync_v2, d1_sync;

ALTER TABLE contract_folder_status DROP COLUMN IF EXISTS search_vector;
DROP INDEX IF EXISTS idx_cp_name_trgm, idx_wp_name_trgm, idx_sc_cfs_updated,
  idx_wp_identifier, idx_tr_cfs_award, idx_cpv_code_prefix;
