AUDIT (
  name clave_existe,
  blocking true
);

-- Every value of a key column exists in the referenced table (the 0/-1
-- placeholder rows included), so inner joins never drop rows.
SELECT f.@columna
FROM @this_model AS f
LEFT JOIN @tabla AS d ON d.@columna = f.@columna
WHERE d.@columna IS NULL
