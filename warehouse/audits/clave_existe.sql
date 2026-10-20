AUDIT (
  name clave_existe,
  blocking true
);

-- Referential integrity: every foreign key of a fact resolves to a member of
-- its dimension (reserved members included), so inner joins never drop rows.
SELECT f.@columna
FROM @this_model AS f
LEFT JOIN @dimension AS d ON d.@columna = f.@columna
WHERE d.@columna IS NULL
