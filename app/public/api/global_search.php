<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';

$pdo=oddb_db();

function gs_table_exists(PDO $pdo,string $table): bool {
    $s=$pdo->prepare("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=:t");
    $s->execute([':t'=>$table]);
    return (int)$s->fetchColumn()>0;
}
function gs_columns(PDO $pdo,string $table): array {
    $s=$pdo->prepare("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=:t");
    $s->execute([':t'=>$table]);
    return array_map(static fn($r)=>$r['column_name'],$s->fetchAll(PDO::FETCH_ASSOC));
}
function gs_first(array $cols,array $candidates): ?string {
    foreach($candidates as $c) if(in_array($c,$cols,true)) return $c;
    return null;
}
function gs_qi(string $id): string {
    if(!preg_match('/^[A-Za-z0-9_]+$/',$id)) throw new RuntimeException('Unsafe SQL identifier.');
    return '`'.$id.'`';
}
function gs_report_schema(PDO $pdo): ?array {
    $table=null;
    foreach(['clinical_report','clinical_reports'] as $t) if(gs_table_exists($pdo,$t)){$table=$t;break;}
    if(!$table)return null;
    $cols=gs_columns($pdo,$table);
    $id=gs_first($cols,['clinical_report_id','report_id','id']);
    $label=gs_first($cols,['title','report_title','name','source_title','source_id']);
    $subtitle=gs_first($cols,['report_type','source','journal','publication_type','status']);
    return $id&&$label?['table'=>$table,'id'=>$id,'label'=>$label,'subtitle'=>$subtitle]:null;
}
function gs_search_simple(PDO $pdo,string $table,string $idCol,string $labelCol,?string $subtitleCol,string $type,string $q,int $limit,bool $prefixOnly=false,array $extraSearch=[]): array {
    if(!gs_table_exists($pdo,$table))return [];
    $cols=gs_columns($pdo,$table);
    if(!in_array($idCol,$cols,true)||!in_array($labelCol,$cols,true))return [];
    $id=gs_qi($idCol);$label=gs_qi($labelCol);
    $searchCols=array_values(array_unique(array_filter(array_merge([$idCol,$labelCol],$extraSearch),static fn($c)=>in_array($c,$cols,true))));
    $where=[];$params=[];
    foreach($searchCols as $i=>$c){
        $ph=':like'.$i;
        $where[]=gs_qi($c)." LIKE $ph";
        $params[$ph]=$prefixOnly?$q.'%':'%'.$q.'%';
    }
    $subtitle="'".$type."'";
    if($subtitleCol&&in_array($subtitleCol,$cols,true))$subtitle="COALESCE(NULLIF(".gs_qi($subtitleCol).",''),'".$type."')";
    $sql="SELECT $id id,$label label,$subtitle subtitle
          FROM ".gs_qi($table)."
          WHERE ".implode(' OR ',$where)."
          ORDER BY CASE WHEN LOWER($label)=LOWER(:exact_label) THEN 0
                        WHEN LOWER($id)=LOWER(:exact_id) THEN 1
                        WHEN LOWER($label) LIKE LOWER(:prefix_label) THEN 2
                        WHEN LOWER($id) LIKE LOWER(:prefix_id) THEN 3 ELSE 4 END,
                   $label
          LIMIT ".(int)$limit;
    $s=$pdo->prepare($sql);
    $params[':exact_label']=$q;
    $params[':exact_id']=$q;
    $params[':prefix_label']=$q.'%';
    $params[':prefix_id']=$q.'%';
    $s->execute($params);
    return array_map(static function($r)use($type){
      return ['type'=>$type,'id'=>(string)$r['id'],'label'=>(string)$r['label'],'subtitle'=>(string)($r['subtitle']??$type)];
    },$s->fetchAll(PDO::FETCH_ASSOC));
}
function gs_search_variant(PDO $pdo,string $q,int $limit): array {
    if(!gs_table_exists($pdo,'variant'))return [];
    $cols=gs_columns($pdo,'variant');
    if(!in_array('variant_id',$cols,true))return [];
    $searchCandidates=['variant_id','clinvar_variation_id','variant_name','rsid','rs_id','hgvs','canonical_hgvs'];
    $searchCols=array_values(array_filter($searchCandidates,static fn($c)=>in_array($c,$cols,true)));
    if(!$searchCols)return [];
    $labelParts=[];
    foreach(['clinvar_variation_id','variant_name','rsid','rs_id','variant_id'] as $c){
        if(in_array($c,$cols,true))$labelParts[]="NULLIF(".gs_qi($c).",'')";
    }
    $labelExpr="COALESCE(".implode(',',$labelParts).")";
    $subtitleParts=[];
    foreach(['clinical_significance','review_status','chromosome'] as $c){
        if(in_array($c,$cols,true))$subtitleParts[]="NULLIF(".gs_qi($c).",'')";
    }
    $subtitleExpr=$subtitleParts?"COALESCE(".implode(',',$subtitleParts).",'variant')":"'variant'";
    $where=[];$params=[];
    foreach($searchCols as $i=>$c){
        $ph=':vprefix'.$i;
        $where[]=gs_qi($c)." LIKE $ph";
        $params[$ph]=$q.'%';
    }
    $sql="SELECT `variant_id` id,$labelExpr label,$subtitleExpr subtitle
          FROM `variant`
          WHERE ".implode(' OR ',$where)."
          ORDER BY CASE WHEN `variant_id`=:vexact THEN 0 ELSE 1 END,`variant_id`
          LIMIT ".(int)$limit;
    $s=$pdo->prepare($sql);
    $params[':vexact']=$q;
    $s->execute($params);
    return array_map(static fn($r)=>[
      'type'=>'variant','id'=>(string)$r['id'],'label'=>(string)($r['label']??$r['id']),
      'subtitle'=>(string)($r['subtitle']??'variant')
    ],$s->fetchAll(PDO::FETCH_ASSOC));
}

$q=trim(qparam('q'));
if(strlen($q)<2)api_error('Enter at least 2 characters.');
$requested=trim(qparam('type'));
$allowed=['disease','gene','variant','drug','trial','report'];
if($requested!==''&&!in_array($requested,$allowed,true))api_error('Unsupported entity type filter.');
$limit=int_param('limit',8,1,15);

$types=$requested!==''?[$requested]:$allowed;
$groups=array_fill_keys($allowed,[]);

foreach($types as $type){
    if($type==='disease'){
        $groups[$type]=gs_search_simple($pdo,'disease','disease_id','disease_name',null,'disease',$q,$limit,false);
    } elseif($type==='gene'){
        $groups[$type]=gs_search_simple($pdo,'gene','hgnc_id','gene_symbol',null,'gene',$q,$limit,false,['hgnc_id']);
    } elseif($type==='variant'){
        // Prefix-only search protects the 700k+ variant table from broad contains scans.
        $groups[$type]=gs_search_variant($pdo,$q,$limit);
    } elseif($type==='drug'){
        $groups[$type]=gs_search_simple($pdo,'drug','drug_id','preferred_name','maximum_clinical_stage','drug',$q,$limit,false,['drug_id']);
    } elseif($type==='trial'){
        $cols=gs_table_exists($pdo,'clinical_trial')?gs_columns($pdo,'clinical_trial'):[];
        $label=in_array('nct_id',$cols,true)?'nct_id':(gs_first($cols,['title','clinical_trial_id'])??'clinical_trial_id');
        $groups[$type]=gs_search_simple($pdo,'clinical_trial','clinical_trial_id',$label,'title','trial',$q,$limit,false,['nct_id','title']);
    } elseif($type==='report'){
        $rs=gs_report_schema($pdo);
        if($rs)$groups[$type]=gs_search_simple($pdo,$rs['table'],$rs['id'],$rs['label'],$rs['subtitle'],'report',$q,$limit,false,[$rs['id']]);
    }
}

$results=[];
foreach($allowed as $t)foreach($groups[$t] as $r)$results[]=$r;

json_response([
 'ok'=>true,'query'=>$q,'type_filter'=>$requested,'groups'=>$groups,'results'=>$results,'total'=>count($results),
 'notes'=>[
  'variant_search'=>'Variant searching is prefix-based for scalability.',
  'clinical'=>'Clinical trials and reports are searchable as independent evidence entities.'
 ]
]);
