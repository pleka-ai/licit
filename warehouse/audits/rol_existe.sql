AUDIT (
  name rol_existe,
  blocking true
);

-- Every value of a key column exists in the referenced table, when the column
-- is named differently from that table's key (adjudicatario_key → empresa_key).
SELECT f.@columna
FROM @this_model AS f
LEFT JOIN @tabla AS d ON d.@clave = f.@columna
WHERE d.@clave IS NULL
