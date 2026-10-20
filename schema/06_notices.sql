-- ValidNoticeInfo -- publication notices

CREATE TABLE IF NOT EXISTS valid_notice_info (
  id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_folder_status_id   uuid NOT NULL REFERENCES contract_folder_status ON DELETE CASCADE,
  notice_type_code            text,
  notice_issue_date           date
);

CREATE INDEX IF NOT EXISTS idx_vni_cfs_id ON valid_notice_info (contract_folder_status_id);

-- PublicationStatus -- media publications (1:N per notice)

CREATE TABLE IF NOT EXISTS publication_status (
  id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  valid_notice_info_id        uuid NOT NULL REFERENCES valid_notice_info ON DELETE CASCADE,
  publication_media_name      text,
  issue_date                  date
);

-- Added after the first deployments: restored state dumps lack it.
ALTER TABLE publication_status ADD COLUMN IF NOT EXISTS issue_date date;

CREATE INDEX IF NOT EXISTS idx_ps_vni_id ON publication_status (valid_notice_info_id);
