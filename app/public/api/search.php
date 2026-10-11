<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';
$pdo=oddb_db();$q=qparam('q');$limit=int_param('limit',20,1,50);
if(mb_strlen($q)<2) json_response(['ok'=>true,'results'=>[]]);
$like=sql_like($q);$results=[];
$searches=[
 ['disease',"SELECT disease_id id,disease_name label,CONCAT_WS(' · ',localization,mondo_id) subtitle
  FROM disease WHERE disease_name LIKE :q1 OR disease_id LIKE :q2 OR mondo_id LIKE :q3 OR omim_id LIKE :q4 OR orphanet_id LIKE :q5 LIMIT {$limit}",
  [':q1'=>$like,':q2'=>$like,':q3'=>$like,':q4'=>$like,':q5'=>$like]],
 ['gene',"SELECT hgnc_id id,gene_symbol label,CONCAT_WS(' · ',gene_name,chromosome_location) subtitle
  FROM gene WHERE gene_symbol LIKE :q1 OR gene_name LIKE :q2 OR hgnc_id LIKE :q3 OR ensembl_gene_id LIKE :q4 LIMIT {$limit}",
  [':q1'=>$like,':q2'=>$like,':q3'=>$like,':q4'=>$like]],
 ['drug',"SELECT drug_id id,preferred_name label,CONCAT_WS(' · ',chembl_id,maximum_clinical_stage) subtitle
  FROM drug WHERE preferred_name LIKE :q1 OR drug_id LIKE :q2 OR chembl_id LIKE :q3 OR drugbank_id LIKE :q4 OR pubchem_cid LIKE :q5 LIMIT {$limit}",
  [':q1'=>$like,':q2'=>$like,':q3'=>$like,':q4'=>$like,':q5'=>$like]],
 ['trial',"SELECT clinical_trial_id id,nct_id label,COALESCE(title,official_title) subtitle
  FROM clinical_trial WHERE nct_id LIKE :q1 OR title LIKE :q2 OR official_title LIKE :q3 LIMIT {$limit}",
  [':q1'=>$like,':q2'=>$like,':q3'=>$like]]
];
foreach($searches as [$type,$sql,$p]){
 $s=$pdo->prepare($sql);$s->execute($p);
 foreach($s->fetchAll() as $r){$r['type']=$type;$results[]=$r;if(count($results)>=$limit)break 2;}
}
if(count($results)<$limit){
 $sql="SELECT variant_id id,COALESCE(NULLIF(clinvar_variation_id,''),variant_id) label,COALESCE(variant_name,hgvs) subtitle
       FROM variant WHERE variant_id LIKE :q1 OR clinvar_variation_id LIKE :q2 OR rs_id LIKE :q3";
 $p=[':q1'=>$like,':q2'=>$like,':q3'=>$like];
 if(mb_strlen($q)>=4){$sql.=" OR hgvs LIKE :q4";$p[':q4']=$like;}
 $sql.=" LIMIT {$limit}";
 $s=$pdo->prepare($sql);$s->execute($p);
 foreach($s->fetchAll() as $r){$r['type']='variant';$results[]=$r;if(count($results)>=$limit)break;}
}
json_response(['ok'=>true,'results'=>$results]);
