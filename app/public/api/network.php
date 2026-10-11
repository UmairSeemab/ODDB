<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';
$pdo=oddb_db();

$mode=qparam('mode','gene');
$etype=qparam('entity_type');
$eid=qparam('entity_id');
$gcat=qparam('gene_category_id');
$cons=qparam('consequence_id');
$phase=qparam('drug_phase');
$direct=qparam('direct','1')!=='0';
$overlap=qparam('overlap','0')==='1';
$target=qparam('target','1')!=='0';
$limit=int_param('limit',250,25,500);

$nodes=[];$edges=[];
function add_node(array &$nodes,string $type,string $id,string $label,array $extra=[]):void{
 if($id==='')return;$key=$type.'::'.$id;
 if(!isset($nodes[$key]))$nodes[$key]=['data'=>array_merge(['id'=>$key,'entity_id'=>$id,'label'=>$label?:$id,'type'=>$type],$extra)];
}
function add_edge(array &$edges,string $id,string $source,string $target,string $type,array $extra=[]):void{
 $edges[]=['data'=>array_merge(['id'=>$id,'source'=>$source,'target'=>$target,'type'=>$type],$extra)];
}

$did=$etype==='disease'?$eid:'';
$gid=$etype==='gene'?$eid:'';
$drid=$etype==='drug'?$eid:'';

if($mode==='gene'){
 if($gcat==='GENE-02'){
  $where=[];$p=[];
  if($did!==''){$where[]="d.disease_id=:did";$p[':did']=$did;}
  $w=$where?'WHERE '.implode(' AND ',$where):'';
  $s=$pdo->prepare("SELECT a.association_id,d.disease_id,d.disease_name,l.locus_id,l.locus_label,
    a.evidence_class,a.evidence_status,a.source,a.pmid,a.doi
    FROM disease_locus_association a
    JOIN disease d ON d.disease_id=a.disease_id
    JOIN locus l ON l.locus_id=a.locus_id {$w} LIMIT {$limit}");
  $s->execute($p);
  foreach($s as $r){
   add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
   add_node($nodes,'locus',$r['locus_id'],$r['locus_label']);
   add_edge($edges,'dla::'.$r['association_id'],'disease::'.$r['disease_id'],'locus::'.$r['locus_id'],'disease_locus',[
    'label'=>'disease–locus','evidence_class'=>$r['evidence_class'],'evidence_status'=>$r['evidence_status'],
    'source_name'=>$r['source'],'pmid'=>$r['pmid'],'doi'=>$r['doi']]);
  }
 }else{
  $where=[];$p=[];
  if($did!==''){$where[]="d.disease_id=:did";$p[':did']=$did;}
  if($gid!==''){$where[]="g.hgnc_id=:gid";$p[':gid']=$gid;}
  if($gcat!==''){$where[]="EXISTS(SELECT 1 FROM gene_category_membership m WHERE m.hgnc_id=g.hgnc_id AND m.gene_category_id=:gcat)";$p[':gcat']=$gcat;}
  $w=$where?'WHERE '.implode(' AND ',$where):'';
  $s=$pdo->prepare("SELECT a.association_id,d.disease_id,d.disease_name,g.hgnc_id,g.gene_symbol,
    a.inheritance,a.evidence_class,a.evidence_status,a.source,a.source_id,a.pmid,a.doi
    FROM disease_gene_association a
    JOIN disease d ON d.disease_id=a.disease_id
    JOIN gene g ON g.hgnc_id=a.hgnc_id {$w}
    ORDER BY d.disease_name,g.gene_symbol LIMIT {$limit}");
  $s->execute($p);
  foreach($s as $r){
   add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
   add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol']);
   add_edge($edges,'dga::'.$r['association_id'],'disease::'.$r['disease_id'],'gene::'.$r['hgnc_id'],'disease_gene',[
    'label'=>$r['inheritance']?:'disease–gene','source_name'=>$r['source'],'source_id'=>$r['source_id'],
    'evidence_class'=>$r['evidence_class'],'evidence_status'=>$r['evidence_status'],'pmid'=>$r['pmid'],'doi'=>$r['doi']]);
  }
 }
}

if($mode==='variant'&&($did!==''||$gid!=='')){
 $where=[];$p=[];
 if($did!==''){$where[]="dva.disease_id=:did";$p[':did']=$did;}
 if($gid!==''){$where[]="gva.hgnc_id=:gid";$p[':gid']=$gid;}
 if($cons!==''){$where[]="EXISTS(SELECT 1 FROM variant_consequence vc2 WHERE vc2.variant_id=v.variant_id AND vc2.consequence_id=:cons)";$p[':cons']=$cons;}
 $w='WHERE '.implode(' AND ',$where);
 $s=$pdo->prepare("SELECT DISTINCT v.variant_id,v.clinvar_variation_id,v.variant_name,v.clinical_significance,
   dva.disease_id,d.disease_name,gva.hgnc_id,g.gene_symbol,dva.mapping_method,dva.evidence_class
   FROM variant v
   LEFT JOIN disease_variant_association dva ON dva.variant_id=v.variant_id
   LEFT JOIN disease d ON d.disease_id=dva.disease_id
   LEFT JOIN gene_variant_association gva ON gva.variant_id=v.variant_id
   LEFT JOIN gene g ON g.hgnc_id=gva.hgnc_id
   {$w} ORDER BY v.clinvar_variation_id LIMIT 80");
 $s->execute($p);
 foreach($s as $r){
  $vl=$r['clinvar_variation_id']?:($r['variant_name']?:$r['variant_id']);
  add_node($nodes,'variant',$r['variant_id'],$vl,['subtitle'=>$r['clinical_significance']]);
  if($r['disease_id']){
   add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
   add_edge($edges,'dva::'.$r['disease_id'].'::'.$r['variant_id'],
    'disease::'.$r['disease_id'],'variant::'.$r['variant_id'],'disease_variant',
    ['label'=>$r['mapping_method']?:'disease–variant','evidence_class'=>$r['evidence_class']]);
  }
  if($r['hgnc_id']){
   add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol']);
   add_edge($edges,'gva::'.$r['hgnc_id'].'::'.$r['variant_id'],
    'gene::'.$r['hgnc_id'],'variant::'.$r['variant_id'],'gene_variant',['label'=>'gene–variant']);
  }
 }
}

if($direct&&$did!==''){
 $p=[':did'=>$did];$phaseSql='';
 if($phase!==''){$phaseSql=" AND dr.maximum_clinical_stage=:phase";$p[':phase']=$phase;}
 $s=$pdo->prepare("SELECT a.disease_drug_association_id,d.disease_id,d.disease_name,dr.drug_id,dr.preferred_name,
   dr.maximum_clinical_stage,a.association_class,a.evidence_strength_class,
   GROUP_CONCAT(DISTINCT e.evidence_subtype SEPARATOR ' | ') evidence_subtypes,
   GROUP_CONCAT(DISTINCT e.source SEPARATOR ' | ') evidence_sources,
   GROUP_CONCAT(DISTINCT e.source_id SEPARATOR ' | ') evidence_source_ids
   FROM disease_drug_association a
   JOIN disease d ON d.disease_id=a.disease_id JOIN drug dr ON dr.drug_id=a.drug_id
   LEFT JOIN disease_drug_evidence e ON e.disease_drug_association_id=a.disease_drug_association_id
   WHERE d.disease_id=:did {$phaseSql}
   GROUP BY a.disease_drug_association_id,d.disease_id,d.disease_name,dr.drug_id,dr.preferred_name,
            dr.maximum_clinical_stage,a.association_class,a.evidence_strength_class LIMIT 150");
 $s->execute($p);
 foreach($s as $r){
  add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
  add_node($nodes,'drug',$r['drug_id'],$r['preferred_name']);
  add_edge($edges,'dda::'.$r['disease_drug_association_id'],'disease::'.$r['disease_id'],'drug::'.$r['drug_id'],'direct_disease_drug',[
   'label'=>$r['evidence_strength_class']?:'direct evidence','association_class'=>$r['association_class'],
   'evidence_subtypes'=>$r['evidence_subtypes'],'evidence_sources'=>$r['evidence_sources'],
   'evidence_source_ids'=>$r['evidence_source_ids'],'clinical_stage'=>$r['maximum_clinical_stage']]);
 }
}

if($target&&($drid!==''||$gid!=='')){
 $where=[];$p=[];
 if($drid!==''){$where[]="dr.drug_id=:drid";$p[':drid']=$drid;}
 if($gid!==''){$where[]="g.hgnc_id=:gid";$p[':gid']=$gid;}
 if($gcat!==''&&$gcat!=='GENE-02'){$where[]="EXISTS(SELECT 1 FROM gene_category_membership m WHERE m.hgnc_id=g.hgnc_id AND m.gene_category_id=:gcat)";$p[':gcat']=$gcat;}
 $w='WHERE '.implode(' AND ',$where);
 $s=$pdo->prepare("SELECT a.drug_target_association_id,dr.drug_id,dr.preferred_name,g.hgnc_id,g.gene_symbol,
   a.mechanism_of_action,a.action_type,a.source,a.source_id
   FROM drug_target_association a JOIN drug dr ON dr.drug_id=a.drug_id JOIN gene g ON g.hgnc_id=a.hgnc_id
   {$w} LIMIT 200");
 $s->execute($p);
 foreach($s as $r){
  add_node($nodes,'drug',$r['drug_id'],$r['preferred_name']);
  add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol']);
  add_edge($edges,'dta::'.$r['drug_target_association_id'],'drug::'.$r['drug_id'],'gene::'.$r['hgnc_id'],'drug_target',[
   'label'=>$r['action_type']?:'target','mechanism_of_action'=>$r['mechanism_of_action'],
   'source_name'=>$r['source'],'source_id'=>$r['source_id']]);
 }
}

if($overlap&&$did!==''){
 $p=[':did'=>$did];$phaseSql='';
 if($phase!==''){$phaseSql=" AND dr.maximum_clinical_stage=:phase";$p[':phase']=$phase;}
 $s=$pdo->prepare("SELECT s.summary_id,d.disease_id,d.disease_name,dr.drug_id,dr.preferred_name,s.target_gene_count,s.target_genes
   FROM disease_drug_target_overlap_summary s JOIN disease d ON d.disease_id=s.disease_id JOIN drug dr ON dr.drug_id=s.drug_id
   WHERE s.direct_disease_drug_evidence=0 AND d.disease_id=:did {$phaseSql} LIMIT 120");
 $s->execute($p);
 foreach($s as $r){
  add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
  add_node($nodes,'drug',$r['drug_id'],$r['preferred_name']);
  add_edge($edges,'overlap::'.$r['summary_id'],'disease::'.$r['disease_id'],'drug::'.$r['drug_id'],'target_overlap_only',[
   'label'=>'target overlap','target_gene_count'=>(int)$r['target_gene_count'],'target_genes'=>$r['target_genes'],
   'warning'=>'Discovery connection only; not direct therapeutic evidence.']);
 }
}
json_response(['ok'=>true,'elements'=>array_merge(array_values($nodes),$edges),
               'counts'=>['nodes'=>count($nodes),'edges'=>count($edges)]]);
