<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';

$pdo=oddb_db();

function parse_ids(string $raw,int $max=30): array {
    if($raw==='') return [];
    $parts=array_values(array_unique(array_filter(array_map('trim',explode(',',$raw)))));
    $out=[];
    foreach($parts as $id){
        if(!preg_match('/^[A-Za-z0-9:._-]+$/',$id)) continue;
        $out[]=$id;
        if(count($out)>=$max) break;
    }
    return $out;
}
function in_clause(array $values,string $prefix,array &$params): string {
    $marks=[];
    foreach(array_values($values) as $i=>$value){
        $key=':'.$prefix.$i;
        $marks[]=$key;
        $params[$key]=$value;
    }
    return $marks?implode(',',$marks):"''";
}
function add_node(array &$nodes,string $type,string $id,string $label,array $extra=[]): void {
    if($id==='') return;
    $key=$type.'::'.$id;
    $base=['id'=>$key,'entity_id'=>$id,'label'=>$label!==''?$label:$id,'type'=>$type,'expanded'=>1];
    if(!isset($nodes[$key])){
        $nodes[$key]=['data'=>array_merge($base,$extra)];
        return;
    }
    $nodes[$key]['data']=array_merge($nodes[$key]['data'],array_filter($extra,static fn($v)=>$v!==null&&$v!==''));
}
function add_edge(array &$edges,string $id,string $source,string $target,string $type,array $extra=[]): void {
    if(isset($edges[$id])) return;
    $edges[$id]=['data'=>array_merge(['id'=>$id,'source'=>$source,'target'=>$target,'type'=>$type],$extra)];
}
function table_exists(PDO $pdo,string $table): bool {
    $s=$pdo->prepare("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=:t");
    $s->execute([':t'=>$table]);
    return (int)$s->fetchColumn()>0;
}
function table_columns(PDO $pdo,string $table): array {
    $s=$pdo->prepare("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=:t ORDER BY ordinal_position");
    $s->execute([':t'=>$table]);
    return array_map(static fn($r)=>$r['column_name'],$s->fetchAll());
}
function first_existing(array $cols,array $candidates): ?string {
    foreach($candidates as $c) if(in_array($c,$cols,true)) return $c;
    return null;
}
function qi(string $id): string {
    if(!preg_match('/^[A-Za-z0-9_]+$/',$id)) throw new RuntimeException('Unsafe SQL identifier.');
    return '`'.$id.'`';
}
function report_schema(PDO $pdo): ?array {
    $reportTable=null;
    foreach(['clinical_report','clinical_reports'] as $t){ if(table_exists($pdo,$t)){ $reportTable=$t; break; } }
    if($reportTable===null) return null;
    $rc=table_columns($pdo,$reportTable);
    $rid=first_existing($rc,['clinical_report_id','report_id','id']);
    if($rid===null) return null;
    $label=first_existing($rc,['title','report_title','name','source_title','source_id',$rid]) ?? $rid;
    $subtitle=first_existing($rc,['report_type','source','journal','publication_type','status']);

    $dAssoc=null;
    foreach(['disease_clinical_report_association','disease_clinical_report','disease_report_association'] as $t){ if(table_exists($pdo,$t)){ $dAssoc=$t; break; } }
    $drAssoc=null;
    foreach(['drug_clinical_report_association','drug_clinical_report','drug_report_association'] as $t){ if(table_exists($pdo,$t)){ $drAssoc=$t; break; } }

    $dReportCol=$dAssoc?first_existing(table_columns($pdo,$dAssoc),['clinical_report_id','report_id']):null;
    $drReportCol=$drAssoc?first_existing(table_columns($pdo,$drAssoc),['clinical_report_id','report_id']):null;

    return [
        'report_table'=>$reportTable,'report_id'=>$rid,'label'=>$label,'subtitle'=>$subtitle,
        'disease_assoc'=>$dAssoc,'disease_report_col'=>$dReportCol,
        'drug_assoc'=>$drAssoc,'drug_report_col'=>$drReportCol
    ];
}

$type=qparam('type');
$relation=qparam('relation');
$ids=parse_ids(qparam('ids'),30);
$limit=int_param('limit',300,25,700);

$allowed=[
 'disease'=>['genes','variants','drugs','trials','reports'],
 'gene'=>['diseases','variants','drugs'],
 'variant'=>['genes','diseases','consequence'],
 'drug'=>['diseases','targets','trials','reports'],
 'trial'=>['diseases','drugs'],
 'report'=>['diseases','drugs']
];
if(!isset($allowed[$type])) api_error('Unsupported entity type.');
if(!in_array($relation,$allowed[$type],true)) api_error('Unsupported expansion relationship.');
if(!$ids) api_error('At least one valid entity id is required.');

$nodes=[];$edges=[];$notice=null;

if($type==='disease'&&$relation==='genes'){
    $p=[];$in=in_clause($ids,'d',$p);
    $s=$pdo->prepare("SELECT a.association_id,d.disease_id,d.disease_name,g.hgnc_id,g.gene_symbol,
      a.inheritance,a.evidence_class,a.evidence_status,a.source,a.source_id,a.pmid,a.doi
      FROM disease_gene_association a JOIN disease d ON d.disease_id=a.disease_id
      JOIN gene g ON g.hgnc_id=a.hgnc_id WHERE d.disease_id IN ($in)
      ORDER BY d.disease_name,g.gene_symbol LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
        add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol']);
        add_edge($edges,'dga::'.$r['association_id'],'disease::'.$r['disease_id'],'gene::'.$r['hgnc_id'],'disease_gene',[
          'label'=>$r['inheritance']?:'disease–gene','evidence_class'=>$r['evidence_class'],'evidence_status'=>$r['evidence_status'],
          'source_name'=>$r['source'],'source_id'=>$r['source_id'],'pmid'=>$r['pmid'],'doi'=>$r['doi']]);
    }
}
if($type==='disease'&&$relation==='variants'){
    $p=[];$in=in_clause($ids,'dv',$p);
    $s=$pdo->prepare("SELECT a.disease_id,d.disease_name,a.variant_id,v.clinvar_variation_id,v.variant_name,
      v.clinical_significance,a.mapping_method,a.evidence_class
      FROM disease_variant_association a JOIN disease d ON d.disease_id=a.disease_id
      JOIN variant v ON v.variant_id=a.variant_id WHERE a.disease_id IN ($in)
      ORDER BY d.disease_name,v.clinvar_variation_id LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        $vl=$r['clinvar_variation_id']?:($r['variant_name']?:$r['variant_id']);
        add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
        add_node($nodes,'variant',$r['variant_id'],$vl,['subtitle'=>$r['clinical_significance']]);
        add_edge($edges,'dva::'.$r['disease_id'].'::'.$r['variant_id'],'disease::'.$r['disease_id'],'variant::'.$r['variant_id'],'disease_variant',[
          'label'=>$r['mapping_method']?:'disease–variant','evidence_class'=>$r['evidence_class']]);
    }
}
if($type==='disease'&&$relation==='drugs'){
    $p=[];$in=in_clause($ids,'dd',$p);
    $s=$pdo->prepare("SELECT a.disease_drug_association_id,d.disease_id,d.disease_name,dr.drug_id,dr.preferred_name,
      dr.maximum_clinical_stage,a.association_class,a.evidence_strength_class,
      GROUP_CONCAT(DISTINCT e.evidence_subtype SEPARATOR ' | ') evidence_subtypes,
      GROUP_CONCAT(DISTINCT e.source SEPARATOR ' | ') evidence_sources,
      GROUP_CONCAT(DISTINCT e.source_id SEPARATOR ' | ') evidence_source_ids
      FROM disease_drug_association a JOIN disease d ON d.disease_id=a.disease_id
      JOIN drug dr ON dr.drug_id=a.drug_id LEFT JOIN disease_drug_evidence e ON e.disease_drug_association_id=a.disease_drug_association_id
      WHERE a.disease_id IN ($in)
      GROUP BY a.disease_drug_association_id,d.disease_id,d.disease_name,dr.drug_id,dr.preferred_name,
      dr.maximum_clinical_stage,a.association_class,a.evidence_strength_class
      ORDER BY d.disease_name,dr.preferred_name LIMIT $limit");
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
if($type==='disease'&&$relation==='trials'){
    $p=[];$in=in_clause($ids,'dt',$p);
    $s=$pdo->prepare("SELECT a.disease_id,d.disease_name,t.clinical_trial_id,t.nct_id,t.title,t.phase,t.overall_status
      FROM disease_clinical_trial_association a JOIN disease d ON d.disease_id=a.disease_id
      JOIN clinical_trial t ON t.clinical_trial_id=a.clinical_trial_id WHERE a.disease_id IN ($in)
      ORDER BY d.disease_name,t.nct_id LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        $tl=$r['nct_id']?:($r['title']?:$r['clinical_trial_id']);
        add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
        add_node($nodes,'trial',$r['clinical_trial_id'],$tl,['subtitle'=>$r['phase']?:$r['overall_status'],'title'=>$r['title']]);
        add_edge($edges,'dtrial::'.$r['disease_id'].'::'.$r['clinical_trial_id'],'disease::'.$r['disease_id'],'trial::'.$r['clinical_trial_id'],'disease_trial',[
          'label'=>'clinical trial association','phase'=>$r['phase'],'overall_status'=>$r['overall_status'],
          'warning'=>'Clinical trial investigation does not by itself establish approval or efficacy.']);
    }
}

if($type==='gene'&&$relation==='diseases'){
    $p=[];$in=in_clause($ids,'gd',$p);
    $s=$pdo->prepare("SELECT a.association_id,d.disease_id,d.disease_name,g.hgnc_id,g.gene_symbol,
      a.inheritance,a.evidence_class,a.evidence_status,a.source,a.source_id,a.pmid,a.doi
      FROM disease_gene_association a JOIN disease d ON d.disease_id=a.disease_id
      JOIN gene g ON g.hgnc_id=a.hgnc_id WHERE a.hgnc_id IN ($in)
      ORDER BY g.gene_symbol,d.disease_name LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol']);
        add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
        add_edge($edges,'dga::'.$r['association_id'],'disease::'.$r['disease_id'],'gene::'.$r['hgnc_id'],'disease_gene',[
          'label'=>$r['inheritance']?:'disease–gene','evidence_class'=>$r['evidence_class'],'evidence_status'=>$r['evidence_status'],
          'source_name'=>$r['source'],'source_id'=>$r['source_id'],'pmid'=>$r['pmid'],'doi'=>$r['doi']]);
    }
}
if($type==='gene'&&$relation==='variants'){
    $p=[];$in=in_clause($ids,'gv',$p);
    $s=$pdo->prepare("SELECT a.hgnc_id,g.gene_symbol,a.variant_id,v.clinvar_variation_id,v.variant_name,v.clinical_significance
      FROM gene_variant_association a JOIN gene g ON g.hgnc_id=a.hgnc_id
      JOIN variant v ON v.variant_id=a.variant_id WHERE a.hgnc_id IN ($in)
      ORDER BY g.gene_symbol,v.clinvar_variation_id LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        $vl=$r['clinvar_variation_id']?:($r['variant_name']?:$r['variant_id']);
        add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol']);
        add_node($nodes,'variant',$r['variant_id'],$vl,['subtitle'=>$r['clinical_significance']]);
        add_edge($edges,'gva::'.$r['hgnc_id'].'::'.$r['variant_id'],'gene::'.$r['hgnc_id'],'variant::'.$r['variant_id'],'gene_variant',['label'=>'gene–variant']);
    }
}
if($type==='gene'&&$relation==='drugs'){
    $p=[];$in=in_clause($ids,'gdr',$p);
    $s=$pdo->prepare("SELECT a.drug_target_association_id,g.hgnc_id,g.gene_symbol,dr.drug_id,dr.preferred_name,
      a.action_type,a.mechanism_of_action,a.source,a.source_id
      FROM drug_target_association a JOIN gene g ON g.hgnc_id=a.hgnc_id
      JOIN drug dr ON dr.drug_id=a.drug_id WHERE a.hgnc_id IN ($in)
      ORDER BY g.gene_symbol,dr.preferred_name LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol']);
        add_node($nodes,'drug',$r['drug_id'],$r['preferred_name']);
        add_edge($edges,'dta::'.$r['drug_target_association_id'],'drug::'.$r['drug_id'],'gene::'.$r['hgnc_id'],'drug_target',[
          'label'=>$r['action_type']?:'target','mechanism_of_action'=>$r['mechanism_of_action'],'source_name'=>$r['source'],'source_id'=>$r['source_id']]);
    }
}

if($type==='variant'&&$relation==='genes'){
    $p=[];$in=in_clause($ids,'vg',$p);
    $s=$pdo->prepare("SELECT a.variant_id,v.clinvar_variation_id,v.variant_name,g.hgnc_id,g.gene_symbol
      FROM gene_variant_association a JOIN variant v ON v.variant_id=a.variant_id
      JOIN gene g ON g.hgnc_id=a.hgnc_id WHERE a.variant_id IN ($in)
      ORDER BY v.clinvar_variation_id,g.gene_symbol LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        $vl=$r['clinvar_variation_id']?:($r['variant_name']?:$r['variant_id']);
        add_node($nodes,'variant',$r['variant_id'],$vl);
        add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol']);
        add_edge($edges,'gva::'.$r['hgnc_id'].'::'.$r['variant_id'],'gene::'.$r['hgnc_id'],'variant::'.$r['variant_id'],'gene_variant',['label'=>'gene–variant']);
    }
}
if($type==='variant'&&$relation==='diseases'){
    $p=[];$in=in_clause($ids,'vd',$p);
    $s=$pdo->prepare("SELECT a.variant_id,v.clinvar_variation_id,v.variant_name,d.disease_id,d.disease_name,a.mapping_method,a.evidence_class
      FROM disease_variant_association a JOIN variant v ON v.variant_id=a.variant_id
      JOIN disease d ON d.disease_id=a.disease_id WHERE a.variant_id IN ($in)
      ORDER BY v.clinvar_variation_id,d.disease_name LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        $vl=$r['clinvar_variation_id']?:($r['variant_name']?:$r['variant_id']);
        add_node($nodes,'variant',$r['variant_id'],$vl);
        add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
        add_edge($edges,'dva::'.$r['disease_id'].'::'.$r['variant_id'],'disease::'.$r['disease_id'],'variant::'.$r['variant_id'],'disease_variant',[
          'label'=>$r['mapping_method']?:'disease–variant','evidence_class'=>$r['evidence_class']]);
    }
}
if($type==='variant'&&$relation==='consequence'){
    $p=[];$in=in_clause($ids,'vc',$p);
    $s=$pdo->prepare("SELECT vc.variant_id,v.clinvar_variation_id,v.variant_name,c.consequence_id,c.consequence_term,vc.source,vc.source_value
      FROM variant_consequence vc JOIN variant v ON v.variant_id=vc.variant_id
      JOIN variant_consequence_category c ON c.consequence_id=vc.consequence_id WHERE vc.variant_id IN ($in)
      ORDER BY v.clinvar_variation_id,c.display_order LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        $vl=$r['clinvar_variation_id']?:($r['variant_name']?:$r['variant_id']);
        add_node($nodes,'variant',$r['variant_id'],$vl);
        add_node($nodes,'consequence',$r['consequence_id'],$r['consequence_term']);
        add_edge($edges,'vc::'.$r['variant_id'].'::'.$r['consequence_id'],'variant::'.$r['variant_id'],'consequence::'.$r['consequence_id'],'variant_consequence',[
          'label'=>'variant consequence','source_name'=>$r['source'],'source_value'=>$r['source_value']]);
    }
}

if($type==='drug'&&$relation==='diseases'){
    $p=[];$in=in_clause($ids,'drd',$p);
    $s=$pdo->prepare("SELECT a.disease_drug_association_id,dr.drug_id,dr.preferred_name,d.disease_id,d.disease_name,
      dr.maximum_clinical_stage,a.association_class,a.evidence_strength_class
      FROM disease_drug_association a JOIN drug dr ON dr.drug_id=a.drug_id JOIN disease d ON d.disease_id=a.disease_id
      WHERE a.drug_id IN ($in) ORDER BY dr.preferred_name,d.disease_name LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        add_node($nodes,'drug',$r['drug_id'],$r['preferred_name']);
        add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
        add_edge($edges,'dda::'.$r['disease_drug_association_id'],'disease::'.$r['disease_id'],'drug::'.$r['drug_id'],'direct_disease_drug',[
          'label'=>$r['evidence_strength_class']?:'direct evidence','association_class'=>$r['association_class'],'clinical_stage'=>$r['maximum_clinical_stage']]);
    }
}
if($type==='drug'&&$relation==='targets'){
    $p=[];$in=in_clause($ids,'drt',$p);
    $s=$pdo->prepare("SELECT a.drug_target_association_id,dr.drug_id,dr.preferred_name,g.hgnc_id,g.gene_symbol,
      a.action_type,a.mechanism_of_action,a.source,a.source_id
      FROM drug_target_association a JOIN drug dr ON dr.drug_id=a.drug_id JOIN gene g ON g.hgnc_id=a.hgnc_id
      WHERE a.drug_id IN ($in) ORDER BY dr.preferred_name,g.gene_symbol LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        add_node($nodes,'drug',$r['drug_id'],$r['preferred_name']);
        add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol']);
        add_edge($edges,'dta::'.$r['drug_target_association_id'],'drug::'.$r['drug_id'],'gene::'.$r['hgnc_id'],'drug_target',[
          'label'=>$r['action_type']?:'target','mechanism_of_action'=>$r['mechanism_of_action'],'source_name'=>$r['source'],'source_id'=>$r['source_id']]);
    }
}
if($type==='drug'&&$relation==='trials'){
    $p=[];$in=in_clause($ids,'drtr',$p);
    $s=$pdo->prepare("SELECT a.drug_id,dr.preferred_name,t.clinical_trial_id,t.nct_id,t.title,t.phase,t.overall_status,a.identity_resolution_status
      FROM drug_clinical_trial_association a JOIN drug dr ON dr.drug_id=a.drug_id
      JOIN clinical_trial t ON t.clinical_trial_id=a.clinical_trial_id WHERE a.drug_id IN ($in)
      ORDER BY dr.preferred_name,t.nct_id LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        $tl=$r['nct_id']?:($r['title']?:$r['clinical_trial_id']);
        add_node($nodes,'drug',$r['drug_id'],$r['preferred_name']);
        add_node($nodes,'trial',$r['clinical_trial_id'],$tl,['subtitle'=>$r['phase']?:$r['overall_status'],'title'=>$r['title']]);
        add_edge($edges,'drtrial::'.$r['drug_id'].'::'.$r['clinical_trial_id'],'drug::'.$r['drug_id'],'trial::'.$r['clinical_trial_id'],'drug_trial',[
          'label'=>'investigated drug','identity_resolution_status'=>$r['identity_resolution_status'],
          'warning'=>'Clinical trial investigation does not by itself establish approval or efficacy.']);
    }
}

if($type==='trial'&&$relation==='diseases'){
    $p=[];$in=in_clause($ids,'trd',$p);
    $s=$pdo->prepare("SELECT t.clinical_trial_id,t.nct_id,t.title,d.disease_id,d.disease_name
      FROM disease_clinical_trial_association a JOIN clinical_trial t ON t.clinical_trial_id=a.clinical_trial_id
      JOIN disease d ON d.disease_id=a.disease_id WHERE a.clinical_trial_id IN ($in)
      ORDER BY t.nct_id,d.disease_name LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        $tl=$r['nct_id']?:($r['title']?:$r['clinical_trial_id']);
        add_node($nodes,'trial',$r['clinical_trial_id'],$tl,['title'=>$r['title']]);
        add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
        add_edge($edges,'dtrial::'.$r['disease_id'].'::'.$r['clinical_trial_id'],'disease::'.$r['disease_id'],'trial::'.$r['clinical_trial_id'],'disease_trial',[
          'label'=>'clinical trial association','warning'=>'Clinical trial investigation does not by itself establish approval or efficacy.']);
    }
}
if($type==='trial'&&$relation==='drugs'){
    $p=[];$in=in_clause($ids,'trdr',$p);
    $s=$pdo->prepare("SELECT t.clinical_trial_id,t.nct_id,t.title,dr.drug_id,dr.preferred_name,a.identity_resolution_status
      FROM drug_clinical_trial_association a JOIN clinical_trial t ON t.clinical_trial_id=a.clinical_trial_id
      JOIN drug dr ON dr.drug_id=a.drug_id WHERE a.clinical_trial_id IN ($in)
      ORDER BY t.nct_id,dr.preferred_name LIMIT $limit");
    $s->execute($p);
    foreach($s as $r){
        $tl=$r['nct_id']?:($r['title']?:$r['clinical_trial_id']);
        add_node($nodes,'trial',$r['clinical_trial_id'],$tl,['title'=>$r['title']]);
        add_node($nodes,'drug',$r['drug_id'],$r['preferred_name']);
        add_edge($edges,'drtrial::'.$r['drug_id'].'::'.$r['clinical_trial_id'],'drug::'.$r['drug_id'],'trial::'.$r['clinical_trial_id'],'drug_trial',[
          'label'=>'investigated drug','identity_resolution_status'=>$r['identity_resolution_status'],
          'warning'=>'Clinical trial investigation does not by itself establish approval or efficacy.']);
    }
}

/* Clinical reports are intentionally modelled through the report entity.
   We never create disease×drug cross-products from a multi-disease/multi-drug report. */
if(($type==='disease'||$type==='drug'||$type==='report')&&($relation==='reports'||$type==='report')){
    $rs=report_schema($pdo);
    if($rs===null){
        $notice='Clinical report tables were not detected in this database build.';
    } else {
        $rt=qi($rs['report_table']);$rid=qi($rs['report_id']);$rlab=qi($rs['label']);
        $rsub=$rs['subtitle']?qi($rs['subtitle']):null;

        if($type==='disease'&&$relation==='reports'){
            if(!$rs['disease_assoc']||!$rs['disease_report_col']) $notice='Disease–clinical-report association table was not detected.';
            else{
                $at=qi($rs['disease_assoc']);$arc=qi($rs['disease_report_col']);$p=[];$in=in_clause($ids,'drep',$p);
                $subsel=$rsub?",r.$rsub report_subtitle":"";
                $sql="SELECT a.disease_id,d.disease_name,r.$rid report_id,r.$rlab report_label $subsel
                      FROM $at a JOIN disease d ON d.disease_id=a.disease_id JOIN $rt r ON r.$rid=a.$arc
                      WHERE a.disease_id IN ($in) ORDER BY d.disease_name,r.$rlab LIMIT $limit";
                $s=$pdo->prepare($sql);$s->execute($p);
                foreach($s as $r){
                    add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
                    add_node($nodes,'report',(string)$r['report_id'],(string)$r['report_label'],['subtitle'=>$r['report_subtitle']??null]);
                    add_edge($edges,'dreport::'.$r['disease_id'].'::'.$r['report_id'],'disease::'.$r['disease_id'],'report::'.$r['report_id'],'disease_report',[
                      'label'=>'clinical report association','warning'=>'Report co-occurrence is preserved through the report entity; it is not an inferred disease–drug treatment pair.']);
                }
            }
        }
        if($type==='drug'&&$relation==='reports'){
            if(!$rs['drug_assoc']||!$rs['drug_report_col']) $notice='Drug–clinical-report association table was not detected.';
            else{
                $at=qi($rs['drug_assoc']);$arc=qi($rs['drug_report_col']);$p=[];$in=in_clause($ids,'drrep',$p);
                $subsel=$rsub?",r.$rsub report_subtitle":"";
                $sql="SELECT a.drug_id,dr.preferred_name,r.$rid report_id,r.$rlab report_label $subsel
                      FROM $at a JOIN drug dr ON dr.drug_id=a.drug_id JOIN $rt r ON r.$rid=a.$arc
                      WHERE a.drug_id IN ($in) ORDER BY dr.preferred_name,r.$rlab LIMIT $limit";
                $s=$pdo->prepare($sql);$s->execute($p);
                foreach($s as $r){
                    add_node($nodes,'drug',$r['drug_id'],$r['preferred_name']);
                    add_node($nodes,'report',(string)$r['report_id'],(string)$r['report_label'],['subtitle'=>$r['report_subtitle']??null]);
                    add_edge($edges,'drreport::'.$r['drug_id'].'::'.$r['report_id'],'drug::'.$r['drug_id'],'report::'.$r['report_id'],'drug_report',[
                      'label'=>'clinical report association','warning'=>'Report co-occurrence is preserved through the report entity; it is not an inferred disease–drug treatment pair.']);
                }
            }
        }
        if($type==='report'&&$relation==='diseases'){
            if(!$rs['disease_assoc']||!$rs['disease_report_col']) $notice='Disease–clinical-report association table was not detected.';
            else{
                $at=qi($rs['disease_assoc']);$arc=qi($rs['disease_report_col']);$p=[];$in=in_clause($ids,'repd',$p);
                $subsel=$rsub?",r.$rsub report_subtitle":"";
                $sql="SELECT r.$rid report_id,r.$rlab report_label $subsel,d.disease_id,d.disease_name
                      FROM $at a JOIN $rt r ON r.$rid=a.$arc JOIN disease d ON d.disease_id=a.disease_id
                      WHERE a.$arc IN ($in) ORDER BY r.$rlab,d.disease_name LIMIT $limit";
                $s=$pdo->prepare($sql);$s->execute($p);
                foreach($s as $r){
                    add_node($nodes,'report',(string)$r['report_id'],(string)$r['report_label'],['subtitle'=>$r['report_subtitle']??null]);
                    add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
                    add_edge($edges,'dreport::'.$r['disease_id'].'::'.$r['report_id'],'disease::'.$r['disease_id'],'report::'.$r['report_id'],'disease_report',[
                      'label'=>'clinical report association','warning'=>'Report co-occurrence is preserved through the report entity; it is not an inferred disease–drug treatment pair.']);
                }
            }
        }
        if($type==='report'&&$relation==='drugs'){
            if(!$rs['drug_assoc']||!$rs['drug_report_col']) $notice='Drug–clinical-report association table was not detected.';
            else{
                $at=qi($rs['drug_assoc']);$arc=qi($rs['drug_report_col']);$p=[];$in=in_clause($ids,'repdr',$p);
                $subsel=$rsub?",r.$rsub report_subtitle":"";
                $sql="SELECT r.$rid report_id,r.$rlab report_label $subsel,dr.drug_id,dr.preferred_name
                      FROM $at a JOIN $rt r ON r.$rid=a.$arc JOIN drug dr ON dr.drug_id=a.drug_id
                      WHERE a.$arc IN ($in) ORDER BY r.$rlab,dr.preferred_name LIMIT $limit";
                $s=$pdo->prepare($sql);$s->execute($p);
                foreach($s as $r){
                    add_node($nodes,'report',(string)$r['report_id'],(string)$r['report_label'],['subtitle'=>$r['report_subtitle']??null]);
                    add_node($nodes,'drug',$r['drug_id'],$r['preferred_name']);
                    add_edge($edges,'drreport::'.$r['drug_id'].'::'.$r['report_id'],'drug::'.$r['drug_id'],'report::'.$r['report_id'],'drug_report',[
                      'label'=>'clinical report association','warning'=>'Report co-occurrence is preserved through the report entity; it is not an inferred disease–drug treatment pair.']);
                }
            }
        }
    }
}

json_response([
 'ok'=>true,
 'type'=>$type,
 'relation'=>$relation,
 'requested_ids'=>$ids,
 'elements'=>array_merge(array_values($nodes),array_values($edges)),
 'counts'=>['nodes'=>count($nodes),'edges'=>count($edges)],
 'notice'=>$notice
]);
