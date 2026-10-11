<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';
$pdo=oddb_db();
$disease=$pdo->query("
 SELECT c.category_id,c.category_system,c.category_name,c.display_order,
        COUNT(DISTINCT m.disease_id) disease_count
 FROM disease_category c
 LEFT JOIN disease_category_membership m ON m.category_id=c.category_id
 GROUP BY c.category_id,c.category_system,c.category_name,c.display_order
 ORDER BY c.category_system,c.display_order")->fetchAll();
$gene=$pdo->query("
 SELECT c.gene_category_id,c.category_name,c.entity_scope,c.display_order,
        CASE WHEN c.entity_scope='locus' THEN (SELECT COUNT(*) FROM locus)
             ELSE COUNT(DISTINCT m.hgnc_id) END entity_count
 FROM gene_category c
 LEFT JOIN gene_category_membership m ON m.gene_category_id=c.gene_category_id
 GROUP BY c.gene_category_id,c.category_name,c.entity_scope,c.display_order
 ORDER BY c.display_order")->fetchAll();
$variant=$pdo->query("
 SELECT c.consequence_id,c.consequence_term,c.display_order,
        COUNT(DISTINCT v.variant_id) variant_count
 FROM variant_consequence_category c
 LEFT JOIN variant_consequence v ON v.consequence_id=c.consequence_id
 GROUP BY c.consequence_id,c.consequence_term,c.display_order
 ORDER BY c.display_order")->fetchAll();
$phase=$pdo->query("
 SELECT maximum_clinical_stage phase,COUNT(*) drug_count
 FROM drug
 WHERE maximum_clinical_stage IS NOT NULL AND maximum_clinical_stage<>''
 GROUP BY maximum_clinical_stage
 ORDER BY CASE WHEN maximum_clinical_stage REGEXP '^[0-9]+([.][0-9]+)?$'
               THEN CAST(maximum_clinical_stage AS DECIMAL(10,2)) ELSE 999 END,
          maximum_clinical_stage")->fetchAll();
json_response(['ok'=>true,'disease_categories'=>$disease,'gene_categories'=>$gene,
               'variant_consequences'=>$variant,'drug_phases'=>$phase]);
