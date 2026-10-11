<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';
$pdo=oddb_db();
$system=qparam('category_system','anatomy');
$category=qparam('category_id');
$mode=qparam('mode','gene');
$gcat=qparam('gene_category_id');
$cons=qparam('consequence_id');
$phase=qparam('drug_phase');
$q=qparam('q');
$limit=int_param('limit',100,1,200);
$offset=int_param('offset',0,0,5000);
if(!in_array($system,['anatomy','inheritance'],true)) api_error('Unsupported category system.');
if(!in_array($mode,['gene','variant'],true)) api_error('Unsupported data mode.');
$where=["c.category_system=:system"];
$params=[':system'=>$system];
if($category!==''){ $where[]="c.category_id=:category";$params[':category']=$category; }
if($q!==''){ $where[]="(d.disease_name LIKE :qn OR d.disease_id LIKE :qi)";$like=sql_like($q);$params[':qn']=$like;$params[':qi']=$like; }
if($mode==='gene'&&$gcat!==''){
    if($gcat==='GENE-02') $where[]="EXISTS(SELECT 1 FROM disease_locus_association x WHERE x.disease_id=d.disease_id)";
    else { $where[]="EXISTS(SELECT 1 FROM disease_gene_association a JOIN gene_category_membership g ON g.hgnc_id=a.hgnc_id WHERE a.disease_id=d.disease_id AND g.gene_category_id=:gcat)";$params[':gcat']=$gcat; }
}
if($mode==='variant'&&$cons!==''){
    $where[]="EXISTS(SELECT 1 FROM disease_variant_association a JOIN variant_consequence v ON v.variant_id=a.variant_id WHERE a.disease_id=d.disease_id AND v.consequence_id=:cons)";
    $params[':cons']=$cons;
}
if($phase!==''){
    $where[]="EXISTS(SELECT 1 FROM disease_drug_association a JOIN drug dr ON dr.drug_id=a.drug_id WHERE a.disease_id=d.disease_id AND dr.maximum_clinical_stage=:phase)";
    $params[':phase']=$phase;
}
$w=implode(' AND ',$where);
$s=$pdo->prepare("SELECT COUNT(DISTINCT d.disease_id)
 FROM disease d JOIN disease_category_membership m ON m.disease_id=d.disease_id
 JOIN disease_category c ON c.category_id=m.category_id WHERE {$w}");
$s->execute($params);$total=(int)$s->fetchColumn();
$s=$pdo->prepare("
 SELECT DISTINCT d.disease_id,d.disease_name,d.localization,d.inheritance,d.mondo_id,
 (SELECT COUNT(DISTINCT x.hgnc_id) FROM disease_gene_association x WHERE x.disease_id=d.disease_id) gene_count,
 (SELECT COUNT(DISTINCT x.variant_id) FROM disease_variant_association x WHERE x.disease_id=d.disease_id) variant_count,
 (SELECT COUNT(DISTINCT x.drug_id) FROM disease_drug_association x WHERE x.disease_id=d.disease_id) drug_count,
 (SELECT COUNT(DISTINCT x.clinical_trial_id) FROM disease_clinical_trial_association x WHERE x.disease_id=d.disease_id) trial_count
 FROM disease d JOIN disease_category_membership m ON m.disease_id=d.disease_id
 JOIN disease_category c ON c.category_id=m.category_id
 WHERE {$w} ORDER BY d.disease_name LIMIT {$limit} OFFSET {$offset}");
$s->execute($params);
json_response(['ok'=>true,'total'=>$total,'diseases'=>$s->fetchAll()]);
