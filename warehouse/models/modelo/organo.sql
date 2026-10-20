MODEL (
  name modelo.organo,
  kind FULL,
  tags (dimension),
  grain organo_key,
  description 'Órgano de contratación (SCD tipo 1: atributos de su publicación más reciente), con la jerarquía administrativa aplanada.',
  audits (
    not_null(columns := (organo_key, nombre)),
    unique_values(columns := (organo_key)),
    unique_values(columns := (id))
  )
);

SELECT
  @clave('organo', p.organo_ref) AS organo_key,
  md5('organo:' || p.organo_ref)::UUID::TEXT AS id,
  p.organo_ref AS referencia_placsp,
  p.name AS nombre,
  p.nif,
  p.dir3,
  p.platform_id AS id_plataforma,
  p.contracting_party_type_code AS tipo_codigo,
  @etiqueta('contracting_authority_type', p.contracting_party_type_code) AS tipo,
  p.activity_code AS actividad_codigo,
  @etiqueta('activity_code', p.activity_code) AS actividad,
  -- CODICE lists parents from the nearest (level 1) up to the root; the
  -- flattened levels below count from the root down.
  json_extract_string(p.parent_hierarchy, '$[0].name') AS organo_padre,
  array_to_string(list_reverse(jerarquia_nombres), ' > ') AS jerarquia,
  list_reverse(jerarquia_nombres)[1] AS jerarquia_nivel_1,
  list_reverse(jerarquia_nombres)[2] AS jerarquia_nivel_2,
  list_reverse(jerarquia_nombres)[3] AS jerarquia_nivel_3,
  list_reverse(jerarquia_nombres)[4] AS jerarquia_nivel_4,
  p.website_uri AS web,
  p.buyer_profile_uri AS perfil_contratante,
  p.address_line AS direccion,
  p.postal_zone AS codigo_postal,
  p.city_name AS ciudad,
  p.country_code AS pais_codigo,
  @etiqueta('country_code', p.country_code) AS pais,
  p.contact_name AS contacto_nombre,
  p.contact_telephone AS contacto_telefono,
  p.contact_email AS contacto_email,
  p.agent_party_id AS agente_id,
  p.agent_party_name AS agente_nombre
FROM (
  SELECT
    *,
    list_filter(json_extract_string(parent_hierarchy, '$[*].name'), x -> x IS NOT NULL)
      AS jerarquia_nombres
  FROM stage.contracting_party
) AS p
UNION ALL
SELECT
  0, NULL, '__desconocido__', 'Órgano desconocido', NULL, NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
  NULL, NULL, NULL, NULL, NULL
