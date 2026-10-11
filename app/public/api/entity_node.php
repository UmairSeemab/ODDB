<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';

$pdo=oddb_db();

function en_table_exists(PDO $pdo,string $table): bool {
    $s=$pdo->prepare("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=:t");
    $s->execute([':t'=>$table]);
    return (int)$s->fetchColumn()>0;
}
function en_columns(PDO $pdo,string $table): array {
    $s=$pdo->prepare("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=:t");
    $s->execute([':t'=>$table]);
    return array_map(static fn($r)=>$r['column_name'],$s->fetchAll(PDO::FETCH_ASSOC));
}
function en_first(array $cols,array $candidates): ?string {
    foreach($candidates as $c) if(in_array($c,$cols,true)) return $c;
    return null;
}
function en_qi(string $id): string {
    if(!preg_match('/^[A-Za-z0-9_]+$/',$id)) throw new RuntimeException('Unsafe SQL identifier.');
    return '`'.$id.'`';
}
function en_report_schema(PDO $pdo): ?array {
    $table=null;
    foreach(['clinical_report','clinical_reports'] as $t) if(en_table_exists($pdo,$t)){$table=$t;break;}
    if(!$table)return null;
    $cols=en_columns($pdo,$table);
    $id=en_first($cols,['clinical_report_id','report_id','id']);
    $label=en_first($cols,['title','report_title','name','source_title','source_id']);
    $subtitle=en_first($cols,['report_type','source','journal','publication_type','status']);
    return $id&&$label?['table'=>$table,'id'=>$id,'label'=>$label,'subtitle'=>$subtitle]:null;
}
function en_fetch(PDO $pdo,string $table,string $idCol,string $labelCol,?string $subtitleCol,string $type,string $id): ?array {
    if(!en_table_exists($pdo,$table))return null;
    $cols=en_columns($pdo,$table);
    if(!in_array($idCol,$cols,true)||!in_array($labelCol,$cols,true))return null;
    $sub=$subtitleCol&&in_array($subtitleCol,$cols,true)?en_qi($subtitleCol)." subtitle":"'".$type."' subtitle";
    $sql="SELECT ".en_qi($idCol)." id,".en_qi($labelCol)." label,$sub
          FROM ".en_qi($table)." WHERE ".en_qi($idCol)."=:id LIMIT 1";
    $s=$pdo->prepare($sql);$s->execute([':id'=>$id]);
    $r=$s->fetch(PDO::FETCH_ASSOC);
    return $r?['type'=>$type,'id'=>(string)$r['id'],'label'=>(string)$r['label'],'subtitle'=>(string)($r['subtitle']??$type)]:null;
}

$type=trim(qparam('type'));$id=trim(qparam('id'));
$allowed=['disease','gene','variant','drug','trial','report'];
if(!in_array($type,$allowed,true))api_error('Unsupported entity type.');
if($id===''||!preg_match('/^[A-Za-z0-9:._-]+$/',$id))api_error('Invalid entity identifier.');

$entity=null;
if($type==='disease')$entity=en_fetch($pdo,'disease','disease_id','disease_name',null,'disease',$id);
elseif($type==='gene')$entity=en_fetch($pdo,'gene','hgnc_id','gene_symbol',null,'gene',$id);
elseif($type==='variant'){
    $cols=en_table_exists($pdo,'variant')?en_columns($pdo,'variant'):[];
    if(in_array('variant_id',$cols,true)){
        $label=en_first($cols,['clinvar_variation_id','variant_name','rsid','rs_id','variant_id'])??'variant_id';
        $sub=en_first($cols,['clinical_significance','review_status']);
        $entity=en_fetch($pdo,'variant','variant_id',$label,$sub,'variant',$id);
        if($entity&&trim($entity['label'])==='')$entity['label']=$id;
    }
}
elseif($type==='drug')$entity=en_fetch($pdo,'drug','drug_id','preferred_name','maximum_clinical_stage','drug',$id);
elseif($type==='trial'){
    $cols=en_table_exists($pdo,'clinical_trial')?en_columns($pdo,'clinical_trial'):[];
    $label=en_first($cols,['nct_id','title','clinical_trial_id'])??'clinical_trial_id';
    $sub=en_first($cols,['title','phase','overall_status']);
    $entity=en_fetch($pdo,'clinical_trial','clinical_trial_id',$label,$sub,'trial',$id);
}
elseif($type==='report'){
    $rs=en_report_schema($pdo);
    if($rs)$entity=en_fetch($pdo,$rs['table'],$rs['id'],$rs['label'],$rs['subtitle'],'report',$id);
}
if(!$entity)api_error('Entity not found.',404);

json_response(['ok'=>true,'entity'=>$entity]);
