<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';
$pdo=oddb_db();
$did=qparam('disease_id');$gid=qparam('gene_id');$cons=qparam('consequence_id');
$page=int_param('page',1,1,100000);$size=int_param('page_size',50,10,100);$offset=($page-1)*$size;
$where=[];$p=[];
if($did!==''){ $where[]="dva.disease_id=:did";$p[':did']=$did; }
if($gid!==''){ $where[]="gva.hgnc_id=:gid";$p[':gid']=$gid; }
if($cons!==''){ $where[]="vc.consequence_id=:cons";$p[':cons']=$cons; }
if(!$where) api_error('At least disease_id or gene_id is required.');
$w=implode(' AND ',$where);
$s=$pdo->prepare("SELECT COUNT(DISTINCT v.variant_id)
 FROM variant v
 LEFT JOIN disease_variant_association dva ON dva.variant_id=v.variant_id
 LEFT JOIN gene_variant_association gva ON gva.variant_id=v.variant_id
 LEFT JOIN variant_consequence vc ON vc.variant_id=v.variant_id
 WHERE {$w}");
$s->execute($p);$total=(int)$s->fetchColumn();
$s=$pdo->prepare("
 SELECT DISTINCT v.variant_id,v.clinvar_variation_id,v.variant_name,v.variant_type,
 v.clinical_significance,v.review_status,v.chromosome,v.position_start,v.position_stop,v.hgvs,v.rs_id,
 GROUP_CONCAT(DISTINCT c.consequence_term ORDER BY c.display_order SEPARATOR ' | ') consequences
 FROM variant v
 LEFT JOIN disease_variant_association dva ON dva.variant_id=v.variant_id
 LEFT JOIN gene_variant_association gva ON gva.variant_id=v.variant_id
 LEFT JOIN variant_consequence vc ON vc.variant_id=v.variant_id
 LEFT JOIN variant_consequence_category c ON c.consequence_id=vc.consequence_id
 WHERE {$w}
 GROUP BY v.variant_id,v.clinvar_variation_id,v.variant_name,v.variant_type,v.clinical_significance,
 v.review_status,v.chromosome,v.position_start,v.position_stop,v.hgvs,v.rs_id
 ORDER BY v.clinvar_variation_id LIMIT {$size} OFFSET {$offset}");
$s->execute($p);
json_response(['ok'=>true,'page'=>$page,'page_size'=>$size,'total'=>$total,'variants'=>$s->fetchAll()]);
