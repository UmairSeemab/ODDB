-- ODDB v1 web taxonomy cleanup
-- Remove the unused "Isolated cases" inheritance category only if it has no memberships.
-- This changes only the web-support taxonomy, not canonical disease data.

SELECT
    c.category_id,
    c.category_name,
    COUNT(m.disease_id) AS membership_count
FROM disease_category c
LEFT JOIN disease_category_membership m
       ON m.category_id = c.category_id
WHERE c.category_id = 'INH-03'
GROUP BY c.category_id, c.category_name;

DELETE c
FROM disease_category c
LEFT JOIN disease_category_membership m
       ON m.category_id = c.category_id
WHERE c.category_id = 'INH-03'
  AND m.disease_id IS NULL;

SELECT category_id, category_name, category_system, display_order
FROM disease_category
WHERE category_system = 'inheritance'
ORDER BY display_order, category_id;
