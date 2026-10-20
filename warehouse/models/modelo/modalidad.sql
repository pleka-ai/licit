MODEL (
  name modelo.modalidad,
  kind FULL,
  grain modalidad_key,
  description 'Dimensión basura con cómo se contrata: tipo y subtipo de contrato, procedimiento, tramitación, sistema, forma de presentación, flags de regulación y financiación, y la plataforma de origen. Solo combinaciones observadas.',
  audits (
    not_null(columns := (modalidad_key)),
    unique_values(columns := (modalidad_key))
  )
);

WITH combinaciones AS (
  SELECT DISTINCT
    type_code, sub_type_code, procedure_code, urgency_code, contracting_system_code,
    submission_method_code, part_presentation_code, over_threshold_indicator,
    auction_constraint_indicator, variant_constraint_indicator, mix_contract_indicator,
    national_legislation_code, funding_program_code, feed_type
  FROM stage.contract_folder_status
)
SELECT
  @modalidad_key() AS modalidad_key,
  type_code AS tipo_contrato_codigo,
  @etiqueta('type_code', type_code) AS tipo_contrato,
  sub_type_code AS subtipo_codigo,
  @etiqueta('sub_type_code', sub_type_code) AS subtipo,
  procedure_code AS procedimiento_codigo,
  @etiqueta('procedure_code', procedure_code) AS procedimiento,
  urgency_code AS tramitacion_codigo,
  @etiqueta('urgency_code', urgency_code) AS tramitacion,
  contracting_system_code AS sistema_contratacion_codigo,
  @etiqueta('contracting_system', contracting_system_code) AS sistema_contratacion,
  submission_method_code AS presentacion_ofertas_codigo,
  @etiqueta('submission_method', submission_method_code) AS presentacion_ofertas,
  part_presentation_code AS presentacion_lotes_codigo,
  @etiqueta('part_presentation', part_presentation_code) AS presentacion_lotes,
  over_threshold_indicator AS regulacion_armonizada,
  auction_constraint_indicator AS subasta_electronica,
  variant_constraint_indicator AS admite_variantes,
  mix_contract_indicator AS contrato_mixto,
  national_legislation_code AS legislacion_codigo,
  @etiqueta('national_legislation', national_legislation_code) AS legislacion,
  funding_program_code AS financiacion_codigo,
  @etiqueta('funding_program', funding_program_code) AS financiacion,
  funding_program_code = 'EU' AS financiacion_ue,
  CASE feed_type
    WHEN 'insiders' THEN 'Perfil alojado en PLACSP'
    WHEN 'outsiders' THEN 'Plataforma autonómica agregada'
    ELSE feed_type
  END AS plataforma
FROM combinaciones
