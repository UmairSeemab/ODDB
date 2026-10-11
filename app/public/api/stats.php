<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';
$pdo=oddb_db();

function scalar(PDO $pdo,string $sql,array $params=[]): int {
    $s=$pdo->prepare($sql);$s->execute($params);return (int)$s->fetchColumn();
}
function rows(PDO $pdo,string $sql,array $params=[]): array {
    $s=$pdo->prepare($sql);$s->execute($params);return $s->fetchAll();
}
function names(array $rows,string $key): array {
    return array_values(array_map(fn($r)=>(string)$r[$key],$rows));
}
function relationship_map(
    string $id,string $title,string $description,
    string $leftLabel,string $rightLabel,
    array $leftNodes,array $rightNodes,array $links,
    string $metricLabel
): array {
    return [
      'id'=>$id,'title'=>$title,'description'=>$description,
      'left_label'=>$leftLabel,'right_label'=>$rightLabel,
      'left_nodes'=>$leftNodes,'right_nodes'=>$rightNodes,
      'links'=>$links,'metric_label'=>$metricLabel
    ];
}

$overview=[
 'diseases'=>scalar($pdo,"SELECT COUNT(*) FROM disease"),
 'genes'=>scalar($pdo,"SELECT COUNT(*) FROM gene"),
 'disease_genes'=>scalar($pdo,"SELECT COUNT(*) FROM disease_gene_association"),
 'variants'=>scalar($pdo,"SELECT COUNT(*) FROM variant"),
 'disease_variants'=>scalar($pdo,"SELECT COUNT(*) FROM disease_variant_association"),
 'drugs'=>scalar($pdo,"SELECT COUNT(*) FROM drug"),
 'drug_targets'=>scalar($pdo,"SELECT COUNT(*) FROM drug_target_association"),
 'disease_drugs'=>scalar($pdo,"SELECT COUNT(*) FROM disease_drug_association"),
 'trials'=>scalar($pdo,"SELECT COUNT(*) FROM clinical_trial"),
 'clinical_reports'=>scalar($pdo,"SELECT COUNT(*) FROM clinical_report")
];

$anatomy=rows($pdo,"
 SELECT c.category_id,c.category_name,COUNT(DISTINCT m.disease_id) disease_count
 FROM disease_category c
 LEFT JOIN disease_category_membership m ON m.category_id=c.category_id
 WHERE c.category_system='anatomy'
 GROUP BY c.category_id,c.category_name,c.display_order
 ORDER BY c.display_order");

$inheritance=rows($pdo,"
 SELECT c.category_id,c.category_name,COUNT(DISTINCT m.disease_id) disease_count
 FROM disease_category c
 LEFT JOIN disease_category_membership m ON m.category_id=c.category_id
 WHERE c.category_system='inheritance'
 GROUP BY c.category_id,c.category_name,c.display_order
 ORDER BY c.display_order");

$inheritanceClassified=scalar($pdo,"
 SELECT COUNT(DISTINCT m.disease_id)
 FROM disease_category_membership m
 JOIN disease_category c ON c.category_id=m.category_id
 WHERE c.category_system='inheritance'");

$geneCategories=rows($pdo,"
 SELECT c.gene_category_id,c.category_name,c.entity_scope,c.display_order,
        CASE WHEN c.entity_scope='locus' THEN (SELECT COUNT(*) FROM locus)
             ELSE COUNT(DISTINCT m.hgnc_id) END entity_count
 FROM gene_category c
 LEFT JOIN gene_category_membership m ON m.gene_category_id=c.gene_category_id
 GROUP BY c.gene_category_id,c.category_name,c.entity_scope,c.display_order
 ORDER BY c.display_order");

$geneOnlyCategories=array_values(array_filter($geneCategories,fn($x)=>$x['entity_scope']==='gene'));

$variantConsequences=rows($pdo,"
 SELECT c.consequence_id,c.consequence_term,c.display_order,
        COUNT(DISTINCT v.variant_id) variant_count
 FROM variant_consequence_category c
 LEFT JOIN variant_consequence v ON v.consequence_id=c.consequence_id
 GROUP BY c.consequence_id,c.consequence_term,c.display_order
 ORDER BY c.display_order");

$zeroConsequences=array_values(array_filter($variantConsequences,fn($x)=>(int)$x['variant_count']===0));

$drugStages=rows($pdo,"
 SELECT CASE
          WHEN maximum_clinical_stage IS NULL OR maximum_clinical_stage='' THEN 'NO_STAGE_REPORTED'
          ELSE maximum_clinical_stage
        END stage,
        COUNT(*) drug_count
 FROM drug
 GROUP BY CASE
          WHEN maximum_clinical_stage IS NULL OR maximum_clinical_stage='' THEN 'NO_STAGE_REPORTED'
          ELSE maximum_clinical_stage
        END
 ORDER BY CASE
  WHEN stage='APPROVAL' THEN 1
  WHEN stage='PHASE_3' THEN 2
  WHEN stage='PHASE_2_3' THEN 3
  WHEN stage='PHASE_2' THEN 4
  WHEN stage='PHASE_1_2' THEN 5
  WHEN stage='PHASE_1' THEN 6
  WHEN stage='UNKNOWN' THEN 98
  WHEN stage='NO_STAGE_REPORTED' THEN 99
  ELSE 97 END,stage");

$overlapPaths=scalar($pdo,"SELECT COUNT(*) FROM disease_drug_target_overlap");
$overlapPairs=scalar($pdo,"SELECT COUNT(*) FROM disease_drug_target_overlap_summary");
$directPlusTarget=scalar($pdo,"SELECT COUNT(*) FROM disease_drug_target_overlap_summary WHERE direct_disease_drug_evidence=1");
$targetOnly=scalar($pdo,"SELECT COUNT(*) FROM disease_drug_target_overlap_summary WHERE direct_disease_drug_evidence=0");
$directWithoutTarget=scalar($pdo,"
 SELECT COUNT(*)
 FROM disease_drug_association d
 WHERE NOT EXISTS (
  SELECT 1 FROM disease_drug_target_overlap_summary s
  WHERE s.disease_id=d.disease_id AND s.drug_id=d.drug_id
 )");

$clinical=[
 'trials'=>$overview['trials'],
 'disease_trial'=>scalar($pdo,"SELECT COUNT(*) FROM disease_clinical_trial_association"),
 'drug_trial'=>scalar($pdo,"SELECT COUNT(*) FROM drug_clinical_trial_association"),
 'reports'=>$overview['clinical_reports'],
 'disease_report'=>scalar($pdo,"SELECT COUNT(*) FROM disease_clinical_report_association"),
 'drug_report'=>scalar($pdo,"SELECT COUNT(*) FROM drug_clinical_report_association")
];

$anatomyGene=rows($pdo,"
 SELECT dc.category_name left_name,gc.category_name right_name,
        COUNT(DISTINCT CONCAT(dga.disease_id,'|',dga.hgnc_id)) association_count
 FROM disease_category dc
 JOIN disease_category_membership dcm ON dcm.category_id=dc.category_id
 JOIN disease_gene_association dga ON dga.disease_id=dcm.disease_id
 JOIN gene_category_membership gcm ON gcm.hgnc_id=dga.hgnc_id
 JOIN gene_category gc ON gc.gene_category_id=gcm.gene_category_id
 WHERE dc.category_system='anatomy' AND gc.entity_scope='gene'
 GROUP BY dc.category_id,dc.category_name,gc.gene_category_id,gc.category_name
 ORDER BY association_count DESC");

$inheritanceGene=rows($pdo,"
 SELECT dc.category_name left_name,gc.category_name right_name,
        COUNT(DISTINCT CONCAT(dga.disease_id,'|',dga.hgnc_id)) association_count
 FROM disease_category dc
 JOIN disease_category_membership dcm ON dcm.category_id=dc.category_id
 JOIN disease_gene_association dga ON dga.disease_id=dcm.disease_id
 JOIN gene_category_membership gcm ON gcm.hgnc_id=dga.hgnc_id
 JOIN gene_category gc ON gc.gene_category_id=gcm.gene_category_id
 WHERE dc.category_system='inheritance' AND gc.entity_scope='gene'
 GROUP BY dc.category_id,dc.category_name,gc.gene_category_id,gc.category_name
 ORDER BY association_count DESC");

$anatomyDrugStage=rows($pdo,"
 SELECT dc.category_name left_name,
        CASE WHEN dr.maximum_clinical_stage IS NULL OR dr.maximum_clinical_stage='' THEN 'NO_STAGE_REPORTED' ELSE dr.maximum_clinical_stage END right_name,
        COUNT(DISTINCT CONCAT(dda.disease_id,'|',dda.drug_id)) association_count
 FROM disease_category dc
 JOIN disease_category_membership dcm ON dcm.category_id=dc.category_id
 JOIN disease_drug_association dda ON dda.disease_id=dcm.disease_id
 JOIN drug dr ON dr.drug_id=dda.drug_id
 WHERE dc.category_system='anatomy'
 GROUP BY dc.category_id,dc.category_name,
          CASE WHEN dr.maximum_clinical_stage IS NULL OR dr.maximum_clinical_stage='' THEN 'NO_STAGE_REPORTED' ELSE dr.maximum_clinical_stage END
 ORDER BY association_count DESC");

$inheritanceDrugStage=rows($pdo,"
 SELECT dc.category_name left_name,
        CASE WHEN dr.maximum_clinical_stage IS NULL OR dr.maximum_clinical_stage='' THEN 'NO_STAGE_REPORTED' ELSE dr.maximum_clinical_stage END right_name,
        COUNT(DISTINCT CONCAT(dda.disease_id,'|',dda.drug_id)) association_count
 FROM disease_category dc
 JOIN disease_category_membership dcm ON dcm.category_id=dc.category_id
 JOIN disease_drug_association dda ON dda.disease_id=dcm.disease_id
 JOIN drug dr ON dr.drug_id=dda.drug_id
 WHERE dc.category_system='inheritance'
 GROUP BY dc.category_id,dc.category_name,
          CASE WHEN dr.maximum_clinical_stage IS NULL OR dr.maximum_clinical_stage='' THEN 'NO_STAGE_REPORTED' ELSE dr.maximum_clinical_stage END
 ORDER BY association_count DESC");

$anatomyVariant=rows($pdo,"
 SELECT dc.category_name left_name,vcc.consequence_term right_name,
        COUNT(DISTINCT CONCAT(dva.disease_id,'|',dva.variant_id,'|',vcc.consequence_id)) association_count
 FROM disease_category dc
 JOIN disease_category_membership dcm ON dcm.category_id=dc.category_id
 JOIN disease_variant_association dva ON dva.disease_id=dcm.disease_id
 JOIN variant_consequence vc ON vc.variant_id=dva.variant_id
 JOIN variant_consequence_category vcc ON vcc.consequence_id=vc.consequence_id
 WHERE dc.category_system='anatomy'
 GROUP BY dc.category_id,dc.category_name,vcc.consequence_id,vcc.consequence_term
 ORDER BY association_count DESC");

$inheritanceVariant=rows($pdo,"
 SELECT dc.category_name left_name,vcc.consequence_term right_name,
        COUNT(DISTINCT CONCAT(dva.disease_id,'|',dva.variant_id,'|',vcc.consequence_id)) association_count
 FROM disease_category dc
 JOIN disease_category_membership dcm ON dcm.category_id=dc.category_id
 JOIN disease_variant_association dva ON dva.disease_id=dcm.disease_id
 JOIN variant_consequence vc ON vc.variant_id=dva.variant_id
 JOIN variant_consequence_category vcc ON vcc.consequence_id=vc.consequence_id
 WHERE dc.category_system='inheritance'
 GROUP BY dc.category_id,dc.category_name,vcc.consequence_id,vcc.consequence_term
 ORDER BY association_count DESC");

$anatomyNames=names($anatomy,'category_name');
$inheritanceNames=names($inheritance,'category_name');
$geneNames=names($geneOnlyCategories,'category_name');
$stageNames=names($drugStages,'stage');
$consequenceNames=names($variantConsequences,'consequence_term');

$relationshipMaps=[
 relationship_map('anatomy_gene','Anatomy ↔ gene category',
  'Disease–gene association connectivity between ocular anatomy categories and gene biotypes.',
  'Anatomy category','Gene category',$anatomyNames,$geneNames,$anatomyGene,'disease–gene associations'),
 relationship_map('inheritance_gene','Inheritance ↔ gene category',
  'Disease–gene association connectivity across directly supported inheritance classes and gene biotypes.',
  'Inheritance category','Gene category',$inheritanceNames,$geneNames,$inheritanceGene,'disease–gene associations'),
 relationship_map('anatomy_drug_stage','Anatomy ↔ drug clinical stage',
  'Direct disease–drug associations connecting anatomy categories with the maximum clinical stage of linked canonical drugs.',
  'Anatomy category','Drug stage',$anatomyNames,$stageNames,$anatomyDrugStage,'direct disease–drug associations'),
 relationship_map('inheritance_drug_stage','Inheritance ↔ drug clinical stage',
  'Direct disease–drug associations connecting supported inheritance categories with drug clinical stage.',
  'Inheritance category','Drug stage',$inheritanceNames,$stageNames,$inheritanceDrugStage,'direct disease–drug associations'),
 relationship_map('anatomy_variant','Anatomy ↔ variant consequence',
  'All 21 consequence categories are retained. Edges count disease–variant links among canonical variants with mapped consequence annotations.',
  'Anatomy category','Variant consequence',$anatomyNames,$consequenceNames,$anatomyVariant,'annotated disease–variant links'),
 relationship_map('inheritance_variant','Inheritance ↔ variant consequence',
  'All 21 consequence categories are retained. Edges connect supported inheritance categories with mapped canonical variant consequences.',
  'Inheritance category','Variant consequence',$inheritanceNames,$consequenceNames,$inheritanceVariant,'annotated disease–variant links')
];

json_response([
 'ok'=>true,
 'release'=>['name'=>'ODDB v1','data_release'=>'2026-09-30'],
 'overview'=>$overview,
 'disease'=>[
  'anatomy'=>$anatomy,'inheritance'=>$inheritance,
  'anatomy_memberships'=>scalar($pdo,"SELECT COUNT(*) FROM disease_category_membership m JOIN disease_category c ON c.category_id=m.category_id WHERE c.category_system='anatomy'"),
  'inheritance_classified'=>$inheritanceClassified,
  'inheritance_unclassified'=>$overview['diseases']-$inheritanceClassified
 ],
 'genetics'=>[
  'gene_categories'=>$geneCategories,
  'variant_consequences'=>$variantConsequences,
  'variants_with_consequence'=>scalar($pdo,"SELECT COUNT(DISTINCT variant_id) FROM variant_consequence"),
  'total_consequence_categories'=>count($variantConsequences),
  'populated_consequence_categories'=>count($variantConsequences)-count($zeroConsequences),
  'zero_consequence_categories'=>$zeroConsequences
 ],
 'therapeutics'=>[
  'drug_stages'=>$drugStages,'direct_disease_drug'=>$overview['disease_drugs'],
  'drug_target'=>$overview['drug_targets'],'overlap_paths'=>$overlapPaths,
  'overlap_pairs'=>$overlapPairs,'direct_plus_target'=>$directPlusTarget,
  'target_only'=>$targetOnly,'direct_without_target'=>$directWithoutTarget
 ],
 'clinical'=>$clinical,
 'relationship_maps'=>$relationshipMaps
]);
