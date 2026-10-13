<?php
declare(strict_types=1);
/** Focused ODDB disease–gene–drug network. Always read-only, bounded, and on-demand. */
require_once __DIR__ . '/db.php';
$pdo = oddb_db();
$did = qparam('disease_id');
$limit = int_param('limit', 80, 10, 200);
if ($did === '' || strlen($did) > 64) api_error('Select a disease.', 400);
$drugMode = qparam('target_overlap', '1') === '1';
function net_rows(PDO $db, string $sql, array $params): array {
    $s = $db->prepare($sql);
    $s->execute($params);
    return $s->fetchAll();
}
$found = net_rows($pdo, 'SELECT disease_id,disease_name FROM disease WHERE disease_id=? LIMIT 1', [$did]);
if (!$found) api_error('Unknown disease.', 404);
$dn = (string)$found[0]['disease_name'];
$nodes = [];
$edges = [];
$addNode = static function(string $type, string $id, string $label) use (&$nodes): string {
    $key = "$type::$id";
    $nodes[$key] = ['id'=>$key, 'type'=>$type, 'label'=>$label, 'entity_id'=>$id];
    return $key;
};
$addEdge = static function(string $source, string $target, string $type, string $label) use (&$edges): void {
    $key = "$source|$target|$type";
    $edges[$key] = ['source'=>$source, 'target'=>$target, 'type'=>$type, 'label'=>$label];
};
$d = $addNode('disease', $did, $dn);
$geneLimit = (int)floor($limit * 0.55);
$drugLimit = (int)floor($limit * 0.22);
$genes = net_rows($pdo, "
    SELECT g.hgnc_id,g.gene_symbol
    FROM disease_gene_association a
    JOIN gene g ON g.hgnc_id=a.hgnc_id
    WHERE a.disease_id=?
    GROUP BY g.hgnc_id,g.gene_symbol
    ORDER BY g.gene_symbol,g.hgnc_id LIMIT $geneLimit", [$did]);
foreach ($genes as $r) {
    $g = $addNode('gene', (string)$r['hgnc_id'], (string)$r['gene_symbol']);
    $addEdge($d,$g,'disease_gene','Disease–gene association');
}
$direct = net_rows($pdo, "
    SELECT dr.drug_id,dr.preferred_name
    FROM disease_drug_association a
    JOIN drug dr ON dr.drug_id=a.drug_id
    WHERE a.disease_id=?
    ORDER BY dr.preferred_name,dr.drug_id LIMIT $drugLimit", [$did]);
foreach ($direct as $r) {
    $drug = $addNode('drug', (string)$r['drug_id'], (string)$r['preferred_name']);
    $addEdge($d,$drug,'direct_disease_drug','Direct disease–drug evidence');
}
if ($drugMode) {
    $overlap = net_rows($pdo, "
        SELECT dr.drug_id,dr.preferred_name
        FROM disease_drug_target_overlap_summary s
        JOIN drug dr ON dr.drug_id=s.drug_id
        WHERE s.disease_id=? AND s.direct_disease_drug_evidence=0
        ORDER BY s.target_gene_count DESC,dr.preferred_name,dr.drug_id LIMIT $drugLimit", [$did]);
    foreach ($overlap as $r) {
        $drug = $addNode('drug', (string)$r['drug_id'], (string)$r['preferred_name']);
        $addEdge($d,$drug,'target_overlap_only','Target overlap only — not a therapeutic claim');
    }
}
// Only connect drug targets when BOTH entities already belong to this focused graph.
// This avoids silently expanding to the full global network.
if (count($genes) && count($nodes)) {
    $targets = net_rows($pdo, "
        SELECT DISTINCT a.drug_id,a.hgnc_id
        FROM drug_target_association a
        JOIN disease_gene_association dg ON dg.hgnc_id=a.hgnc_id
        WHERE dg.disease_id=? LIMIT 10000", [$did]);
    foreach ($targets as $r) {
        $drugKey = 'drug::'.$r['drug_id'];
        $geneKey = 'gene::'.$r['hgnc_id'];
        if (isset($nodes[$drugKey]) && isset($nodes[$geneKey])) {
            $addEdge($geneKey,$drugKey,'drug_target','Curated drug–target association');
        }
    }
}
header('Cache-Control: public,max-age=300');
json_response([
    'ok'=>true,'disease'=>['id'=>$did,'name'=>$dn],
    'nodes'=>array_values($nodes),'edges'=>array_values($edges),
    'counts'=>['nodes'=>count($nodes),'edges'=>count($edges)],
    'note'=>'Target-overlap-only is a discovery connection, not direct treatment evidence.'
]);
