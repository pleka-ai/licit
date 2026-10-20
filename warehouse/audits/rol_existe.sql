AUDIT (
  name rol_existe,
  blocking true
);

-- Referential integrity for a role-playing foreign key, whose column name
-- differs from the dimension's key (e.g. adjudicatario_key → empresa_key).
SELECT f.@columna
FROM @this_model AS f
LEFT JOIN @dimension AS d ON d.@clave = f.@columna
WHERE d.@clave IS NULL
