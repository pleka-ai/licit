MODEL (
  name stage.borme_filing,
  kind VIEW,
  grain (doc_id, number),
  description 'Anuncios de la sección A del BORME (un empresario por anuncio), con la identidad registral de la sociedad.'
);

SELECT
  doc_id::TEXT AS doc_id,
  number::BIGINT AS number,
  province::TEXT AS province,
  published::DATE AS published,
  @texto(company) AS company,
  @nombre_normalizado(company) AS company_normalized,
  @texto(text) AS text,
  @texto(volume) AS volume,
  @texto(page) AS page,
  @texto(section) AS section,
  @texto(sheet) AS sheet,
  @texto(entry) AS entry,
  @fecha(entry_date) AS entry_date,
  -- The registry sheet identifies a company within its registry; without it
  -- (under 1 % of filings) the normalized name does.
  coalesce('hoja:' || @texto(sheet), 'nombre:' || @nombre_normalizado(company))
    AS sociedad_ref
FROM @borme(filing)
WHERE @texto(company) IS NOT NULL
