<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';
$pdo=oddb_db();$type=qparam('type');$id=qparam('id');
if($type===''||$id==='')api_error('type and id are required.');
function one(PDO $p,string $sql,array $a):?array{$s=$p->prepare($sql);$s->execute($a);$r=$s->fetch();return $r?:null;}
function many(PDO $p,string $sql,array $a):array{$s=$p->prepare($sql);$s->execute($a);return $s->fetchAll();}
function links(PDO $p,string $t,string $id):array{return many($p,"
 SELECT resource_name,external_id,url,display_label,source FROM entity_external_link
 WHERE entity_type=:t AND entity_id=:id ORDER BY display_order,resource_name",[':t'=>$t,':id'=>$id]);}

if($type==='disease'){
 $e=one($pdo,"SELECT * FROM disease WHERE disease_id=:id",[':id'=>$id]);if(!$e)api_error('Disease not found.',404);
 $g=many($pdo,"SELECT x.hgnc_id id,x.gene_symbol label,x.gene_name,a.inheritance,a.evidence_class,a.pmid,a.doi,a.source
 FROM disease_gene_association a JOIN gene x ON x.hgnc_id=a.hgnc_id WHERE a.disease_id=:id ORDER BY x.gene_symbol LIMIT 150",[':id'=>$id]);
 $dr=many($pdo,"SELECT x.drug_id id,x.preferred_name label,a.evidence_strength_class,a.association_class,x.maximum_clinical_stage
 FROM disease_drug_association a JOIN drug x ON x.drug_id=a.drug_id WHERE a.disease_id=:id ORDER BY x.preferred_name LIMIT 150",[':id'=>$id]);
 $tr=many($pdo,"SELECT x.clinical_trial_id id,x.nct_id label,x.title,x.phase,x.overall_status
 FROM disease_clinical_trial_association a JOIN clinical_trial x ON x.clinical_trial_id=a.clinical_trial_id
 WHERE a.disease_id=:id ORDER BY x.nct_id LIMIT 150",[':id'=>$id]);
 $vc=(int)one($pdo,"SELECT COUNT(*) n FROM disease_variant_association WHERE disease_id=:id",[':id'=>$id])['n'];
 json_response(['ok'=>true,'type'=>'disease','entity'=>$e,'external_links'=>links($pdo,'disease',$id),
 'related'=>['genes'=>$g,'drugs'=>$dr,'trials'=>$tr,'variant_count'=>$vc]]);
}
if($type==='gene'){
 $e=one($pdo,"SELECT * FROM gene WHERE hgnc_id=:id",[':id'=>$id]);if(!$e)api_error('Gene not found.',404);
 $d=many($pdo,"SELECT x.disease_id id,x.disease_name label,a.inheritance,a.evidence_class,a.pmid,a.doi,a.source
 FROM disease_gene_association a JOIN disease x ON x.disease_id=a.disease_id WHERE a.hgnc_id=:id ORDER BY x.disease_name LIMIT 150",[':id'=>$id]);
 $dr=many($pdo,"SELECT x.drug_id id,x.preferred_name label,a.action_type,a.mechanism_of_action,a.source
 FROM drug_target_association a JOIN drug x ON x.drug_id=a.drug_id WHERE a.hgnc_id=:id ORDER BY x.preferred_name LIMIT 150",[':id'=>$id]);
 $vc=(int)one($pdo,"SELECT COUNT(*) n FROM gene_variant_association WHERE hgnc_id=:id",[':id'=>$id])['n'];
 json_response(['ok'=>true,'type'=>'gene','entity'=>$e,'external_links'=>links($pdo,'gene',$id),
 'related'=>['diseases'=>$d,'drugs'=>$dr,'variant_count'=>$vc]]);
}
if($type==='locus'){
 $e=one($pdo,"SELECT * FROM locus WHERE locus_id=:id",[':id'=>$id]);if(!$e)api_error('Locus not found.',404);
 $d=many($pdo,"SELECT x.disease_id id,x.disease_name label,a.evidence_class,a.evidence_status,a.pmid,a.doi,a.source
 FROM disease_locus_association a JOIN disease x ON x.disease_id=a.disease_id WHERE a.locus_id=:id ORDER BY x.disease_name",[':id'=>$id]);
 json_response(['ok'=>true,'type'=>'locus','entity'=>$e,'external_links'=>links($pdo,'locus',$id),'related'=>['diseases'=>$d]]);
}
if($type==='drug'){
 $e=one($pdo,"SELECT * FROM drug WHERE drug_id=:id",[':id'=>$id]);if(!$e)api_error('Drug not found.',404);
 $d=many($pdo,"SELECT x.disease_id id,x.disease_name label,a.evidence_strength_class,a.association_class
 FROM disease_drug_association a JOIN disease x ON x.disease_id=a.disease_id WHERE a.drug_id=:id ORDER BY x.disease_name LIMIT 150",[':id'=>$id]);
 $t=many($pdo,"SELECT g.hgnc_id id,g.gene_symbol label,a.action_type,a.mechanism_of_action,a.source
 FROM drug_target_association a JOIN gene g ON g.hgnc_id=a.hgnc_id WHERE a.drug_id=:id ORDER BY g.gene_symbol LIMIT 150",[':id'=>$id]);
 $tr=many($pdo,"SELECT x.clinical_trial_id id,x.nct_id label,x.title,x.phase,x.overall_status,a.identity_resolution_status
 FROM drug_clinical_trial_association a JOIN clinical_trial x ON x.clinical_trial_id=a.clinical_trial_id
 WHERE a.drug_id=:id ORDER BY x.nct_id LIMIT 150",[':id'=>$id]);
 json_response(['ok'=>true,'type'=>'drug','entity'=>$e,'external_links'=>links($pdo,'drug',$id),
 'related'=>['diseases'=>$d,'targets'=>$t,'trials'=>$tr]]);
}
if($type==='trial'){
 $e=one($pdo,"SELECT * FROM clinical_trial WHERE clinical_trial_id=:id",[':id'=>$id]);if(!$e)api_error('Trial not found.',404);
 $d=many($pdo,"SELECT x.disease_id id,x.disease_name label FROM disease_clinical_trial_association a
 JOIN disease x ON x.disease_id=a.disease_id WHERE a.clinical_trial_id=:id ORDER BY x.disease_name",[':id'=>$id]);
 $dr=many($pdo,"SELECT x.drug_id id,x.preferred_name label,a.identity_resolution_status
 FROM drug_clinical_trial_association a JOIN drug x ON x.drug_id=a.drug_id WHERE a.clinical_trial_id=:id ORDER BY x.preferred_name",[':id'=>$id]);
 json_response(['ok'=>true,'type'=>'trial','entity'=>$e,'external_links'=>links($pdo,'trial',$id),'related'=>['diseases'=>$d,'drugs'=>$dr]]);
}
if($type==='variant'){
 $e=one($pdo,"SELECT * FROM variant WHERE variant_id=:id",[':id'=>$id]);if(!$e)api_error('Variant not found.',404);
 $g=many($pdo,"SELECT x.hgnc_id id,x.gene_symbol label FROM gene_variant_association a
 JOIN gene x ON x.hgnc_id=a.hgnc_id WHERE a.variant_id=:id ORDER BY x.gene_symbol",[':id'=>$id]);
 $d=many($pdo,"SELECT x.disease_id id,x.disease_name label,a.mapping_method,a.evidence_class
 FROM disease_variant_association a JOIN disease x ON x.disease_id=a.disease_id WHERE a.variant_id=:id ORDER BY x.disease_name",[':id'=>$id]);
 $c=many($pdo,"SELECT c.consequence_term,v.source,v.source_value FROM variant_consequence v
 JOIN variant_consequence_category c ON c.consequence_id=v.consequence_id WHERE v.variant_id=:id ORDER BY c.display_order",[':id'=>$id]);
 json_response(['ok'=>true,'type'=>'variant','entity'=>$e,'external_links'=>links($pdo,'variant',$id),
 'related'=>['genes'=>$g,'diseases'=>$d,'consequences'=>$c]]);
}
api_error('Unsupported entity type.',400);
