MODEL (
  name stage.contracting_party,
  kind VIEW,
  grain organo_ref,
  description 'Órgano de contratación, versión del expediente más reciente que lo cita.'
);

SELECT
  @texto(organo_ref) AS organo_ref,
  updated::TIMESTAMPTZ AS updated,
  @texto(name) AS name,
  @texto(dir3) AS dir3,
  @texto(nif) AS nif,
  @texto(platform_id) AS platform_id,
  @texto(website_uri) AS website_uri,
  contracting_party_type_code::TEXT AS contracting_party_type_code,
  activity_code::TEXT AS activity_code,
  @texto(buyer_profile_uri) AS buyer_profile_uri,
  @texto(contact_name) AS contact_name,
  @texto(contact_telephone) AS contact_telephone,
  @texto(contact_telefax) AS contact_telefax,
  @texto(contact_email) AS contact_email,
  @texto(city_name) AS city_name,
  @texto(postal_zone) AS postal_zone,
  @texto(address_line) AS address_line,
  country_code::TEXT AS country_code,
  @texto(agent_party_id) AS agent_party_id,
  @texto(agent_party_name) AS agent_party_name,
  parent_hierarchy::JSON AS parent_hierarchy
FROM @raw(contracting_party)
WHERE @texto(organo_ref) IS NOT NULL
