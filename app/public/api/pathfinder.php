<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';

$pdo=oddb_db();

function pf_table_exists(PDO $pdo,string $table): bool {
    $s=$pdo->prepare("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=:t");
    $s->execute([':t'=>$table]);
    return (int)$s->fetchColumn()>0;
}
function pf_columns(PDO $pdo,string $table): array {
    $s=$pdo->prepare("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=:t");
    $s->execute([':t'=>$table]);
    return array_map(static fn($r)=>$r['column_name'],$s->fetchAll(PDO::FETCH_ASSOC));
}
function pf_first(array $cols,array $candidates): ?string {
    foreach($candidates as $x) if(in_array($x,$cols,true)) return $x;
    return null;
}
function pf_qi(string $id): string {
    if(!preg_match('/^[A-Za-z0-9_]+$/',$id)) throw new RuntimeException('Unsafe SQL identifier.');
    return '`'.$id.'`';
}
function pf_valid_id(string $id): bool {
    return $id!=='' && (bool)preg_match('/^[A-Za-z0-9:._-]+$/',$id);
}
function pf_report_schema(PDO $pdo): ?array {
    $rt=null;
    foreach(['clinical_report','clinical_reports'] as $t) if(pf_table_exists($pdo,$t)){$rt=$t;break;}
    if(!$rt)return null;
    $rc=pf_columns($pdo,$rt);
    $rid=pf_first($rc,['clinical_report_id','report_id','id']);
    if(!$rid)return null;
    $label=pf_first($rc,['title','report_title','name','source_title','source_id',$rid])??$rid;
    $subtitle=pf_first($rc,['report_type','source','journal','publication_type','status']);
    $da=null;$dra=null;
    foreach(['disease_clinical_report_association','disease_clinical_report','disease_report_association'] as $t) if(pf_table_exists($pdo,$t)){$da=$t;break;}
    foreach(['drug_clinical_report_association','drug_clinical_report','drug_report_association'] as $t) if(pf_table_exists($pdo,$t)){$dra=$t;break;}
    return [
      'table'=>$rt,'id'=>$rid,'label'=>$label,'subtitle'=>$subtitle,
      'disease_assoc'=>$da,
      'disease_report_col'=>$da?pf_first(pf_columns($pdo,$da),['clinical_report_id','report_id']):null,
      'drug_assoc'=>$dra,
      'drug_report_col'=>$dra?pf_first(pf_columns($pdo,$dra),['clinical_report_id','report_id']):null
    ];
}
function pf_specs(PDO $pdo): array {
    $s=[];
    if(pf_table_exists($pdo,'disease_gene_association'))$s['disease_gene']=[
      'table'=>'disease_gene_association','left_type'=>'disease','left_col'=>'disease_id','right_type'=>'gene','right_col'=>'hgnc_id',
      'pk'=>'association_id','prefix'=>'dga','label'=>'Disease–gene association','semantic'=>'genetic association','priority'=>10,
      'meta'=>['inheritance'=>'inheritance','evidence_class'=>'evidence_class','evidence_status'=>'evidence_status','source'=>'source','source_id'=>'source_id','pmid'=>'pmid','doi'=>'doi'],
      'warning'=>null
    ];
    if(pf_table_exists($pdo,'disease_variant_association'))$s['disease_variant']=[
      'table'=>'disease_variant_association','left_type'=>'disease','left_col'=>'disease_id','right_type'=>'variant','right_col'=>'variant_id',
      'pk'=>null,'prefix'=>'dva','label'=>'Explicit disease–variant association','semantic'=>'explicit variant association','priority'=>11,
      'meta'=>['mapping_method'=>'mapping_method','evidence_class'=>'evidence_class'],
      'warning'=>'This path uses an explicit disease_variant_association row; no disease–variant link is inferred through a gene.'
    ];
    if(pf_table_exists($pdo,'gene_variant_association'))$s['gene_variant']=[
      'table'=>'gene_variant_association','left_type'=>'gene','left_col'=>'hgnc_id','right_type'=>'variant','right_col'=>'variant_id',
      'pk'=>null,'prefix'=>'gva','label'=>'Gene–variant association','semantic'=>'gene–variant relationship','priority'=>12,
      'meta'=>[],'warning'=>null
    ];
    if(pf_table_exists($pdo,'disease_drug_association'))$s['direct_disease_drug']=[
      'table'=>'disease_drug_association','left_type'=>'disease','left_col'=>'disease_id','right_type'=>'drug','right_col'=>'drug_id',
      'pk'=>'disease_drug_association_id','prefix'=>'dda','label'=>'Direct disease–drug evidence','semantic'=>'direct therapeutic evidence','priority'=>1,
      'meta'=>['association_class'=>'association_class','evidence_strength_class'=>'evidence_strength_class'],
      'warning'=>'Direct disease-specific therapeutic evidence is distinct from target-overlap discovery.'
    ];
    if(pf_table_exists($pdo,'drug_target_association'))$s['drug_target']=[
      'table'=>'drug_target_association','left_type'=>'drug','left_col'=>'drug_id','right_type'=>'gene','right_col'=>'hgnc_id',
      'pk'=>'drug_target_association_id','prefix'=>'dta','label'=>'Drug–target relationship','semantic'=>'molecular pharmacology','priority'=>13,
      'meta'=>['action_type'=>'action_type','mechanism_of_action'=>'mechanism_of_action','source'=>'source','source_id'=>'source_id'],
      'warning'=>'A drug–target relationship is molecular pharmacology and does not by itself establish treatment of a disease.'
    ];
    if(pf_table_exists($pdo,'disease_drug_target_overlap_summary'))$s['target_overlap_only']=[
      'table'=>'disease_drug_target_overlap_summary','left_type'=>'disease','left_col'=>'disease_id','right_type'=>'drug','right_col'=>'drug_id',
      'pk'=>'summary_id','prefix'=>'overlap','label'=>'Target-overlap discovery','semantic'=>'discovery-only target overlap','priority'=>30,
      'condition'=>'direct_disease_drug_evidence=0',
      'meta'=>['target_gene_count'=>'target_gene_count','target_genes'=>'target_genes'],
      'warning'=>'Discovery connection only; this is not direct therapeutic evidence.'
    ];
    if(pf_table_exists($pdo,'disease_clinical_trial_association'))$s['disease_trial']=[
      'table'=>'disease_clinical_trial_association','left_type'=>'disease','left_col'=>'disease_id','right_type'=>'trial','right_col'=>'clinical_trial_id',
      'pk'=>null,'prefix'=>'dtrial','label'=>'Disease–clinical trial association','semantic'=>'clinical trial context','priority'=>40,
      'meta'=>[],'warning'=>'Trial investigation does not by itself establish approval or efficacy.'
    ];
    if(pf_table_exists($pdo,'drug_clinical_trial_association'))$s['drug_trial']=[
      'table'=>'drug_clinical_trial_association','left_type'=>'drug','left_col'=>'drug_id','right_type'=>'trial','right_col'=>'clinical_trial_id',
      'pk'=>null,'prefix'=>'drtrial','label'=>'Drug–clinical trial association','semantic'=>'clinical trial context','priority'=>41,
      'meta'=>['identity_resolution_status'=>'identity_resolution_status'],
      'warning'=>'Trial co-occurrence is preserved through the trial entity and is not a direct disease–drug treatment assertion.'
    ];
    $rs=pf_report_schema($pdo);
    if($rs&&$rs['disease_assoc']&&$rs['disease_report_col'])$s['disease_report']=[
      'table'=>$rs['disease_assoc'],'left_type'=>'disease','left_col'=>'disease_id','right_type'=>'report','right_col'=>$rs['disease_report_col'],
      'pk'=>null,'prefix'=>'dreport','label'=>'Disease–clinical report association','semantic'=>'clinical report context','priority'=>45,
      'meta'=>[],'warning'=>'Report co-occurrence is preserved through the report entity and is not a direct disease–drug treatment assertion.'
    ];
    if($rs&&$rs['drug_assoc']&&$rs['drug_report_col'])$s['drug_report']=[
      'table'=>$rs['drug_assoc'],'left_type'=>'drug','left_col'=>'drug_id','right_type'=>'report','right_col'=>$rs['drug_report_col'],
      'pk'=>null,'prefix'=>'drreport','label'=>'Drug–clinical report association','semantic'=>'clinical report context','priority'=>46,
      'meta'=>[],'warning'=>'Report co-occurrence is preserved through the report entity and is not a direct disease–drug treatment assertion.'
    ];
    return $s;
}
function pf_entity(PDO $pdo,string $type,string $id,?array $rs,array &$cache): array {
    $k=$type.'::'.$id;
    if(isset($cache[$k]))return $cache[$k];
    $label=$id;$subtitle=null;
    if($type==='disease'){
        $q=$pdo->prepare("SELECT disease_name label FROM disease WHERE disease_id=:id");$q->execute([':id'=>$id]);
    } elseif($type==='gene'){
        $q=$pdo->prepare("SELECT gene_symbol label FROM gene WHERE hgnc_id=:id");$q->execute([':id'=>$id]);
    } elseif($type==='variant'){
        $q=$pdo->prepare("SELECT COALESCE(NULLIF(clinvar_variation_id,''),NULLIF(variant_name,''),variant_id) label,clinical_significance subtitle FROM variant WHERE variant_id=:id");$q->execute([':id'=>$id]);
    } elseif($type==='drug'){
        $q=$pdo->prepare("SELECT preferred_name label,maximum_clinical_stage subtitle FROM drug WHERE drug_id=:id");$q->execute([':id'=>$id]);
    } elseif($type==='trial'){
        $q=$pdo->prepare("SELECT COALESCE(NULLIF(nct_id,''),NULLIF(title,''),clinical_trial_id) label,COALESCE(NULLIF(phase,''),overall_status) subtitle,title FROM clinical_trial WHERE clinical_trial_id=:id");$q->execute([':id'=>$id]);
    } elseif($type==='report'&&$rs){
        $t=pf_qi($rs['table']);$rid=pf_qi($rs['id']);$rl=pf_qi($rs['label']);$sub=$rs['subtitle']?','.pf_qi($rs['subtitle']).' subtitle':'';
        $q=$pdo->prepare("SELECT $rl label $sub FROM $t WHERE $rid=:id");$q->execute([':id'=>$id]);
    } else {
        return $cache[$k]=['type'=>$type,'id'=>$id,'label'=>$id,'subtitle'=>null];
    }
    $r=$q->fetch(PDO::FETCH_ASSOC);
    if($r){$label=(string)($r['label']??$id);$subtitle=$r['subtitle']??null;}
    return $cache[$k]=['type'=>$type,'id'=>$id,'label'=>$label!==''?$label:$id,'subtitle'=>$subtitle];
}
function pf_routes(array $specs,string $from,string $to,int $maxLen): array {
    $routes=[];
    $dfs=function(string $cur,array $seq,array $types) use (&$dfs,&$routes,$specs,$to,$maxLen,$from){
        $depth=count($seq);
        if($depth>0&&$cur===$to){
            $score=0;foreach($seq as $x)$score+=(int)$specs[$x['name']]['priority'];
            $routes[]=['steps'=>$seq,'types'=>$types,'score'=>$score];
            return;
        }
        if($depth>=$maxLen)return;
        foreach($specs as $name=>$sp){
            $orient=null;$next=null;
            if($sp['left_type']===$cur){$orient='+';$next=$sp['right_type'];}
            elseif($sp['right_type']===$cur){$orient='-';$next=$sp['left_type'];}
            else continue;

            // Avoid using variants as broad intermediate hubs unless a requested endpoint is a variant.
            if($next==='variant' && $to!=='variant' && $from!=='variant' && $depth>=1) continue;

            // Simple type paths; allow returning to the start type only when it is the requested target.
            if(in_array($next,$types,true) && !($next===$to && $depth+1>=2)) continue;

            // Do not bounce immediately across the same physical relationship to the same type.
            if($seq){
                $last=$seq[count($seq)-1];
                if($last['name']===$name && $next===$types[count($types)-2] && $next!==$to)continue;
            }
            $nseq=$seq;$nseq[]=['name'=>$name,'orientation'=>$orient];
            $nt=$types;$nt[]=$next;
            $dfs($next,$nseq,$nt);
        }
    };
    $dfs($from,[],[$from]);
    usort($routes,static function($a,$b){
        $la=count($a['steps']);$lb=count($b['steps']);
        return ($la<=>$lb) ?: ($a['score']<=>$b['score']);
    });
    $out=[];$seen=[];
    foreach($routes as $r){
        $k=implode('>',array_map(static fn($x)=>$x['name'].':'.$x['orientation'],$r['steps']));
        if(isset($seen[$k]))continue;$seen[$k]=1;$out[]=$r;
        if(count($out)>=36)break;
    }
    return $out;
}
function pf_query_route(PDO $pdo,array $route,array $specs,string $fromId,string $toId,int $limit): array {
    $steps=$route['steps'];$select=[];$where=[];$joins=[];$params=[':from_id'=>$fromId,':to_id'=>$toId];
    $prevEndpointExpr=null;$startExpr=null;$endExpr=null;
    foreach($steps as $i=>$step){
        $sp=$specs[$step['name']];$a='r'.$i;
        $plus=$step['orientation']==='+';
        $startCol=$plus?$sp['left_col']:$sp['right_col'];
        $endCol=$plus?$sp['right_col']:$sp['left_col'];
        $table=pf_qi($sp['table']);$qStart=pf_qi($startCol);$qEnd=pf_qi($endCol);
        if($i===0){
            $from="$table $a";$startExpr="$a.$qStart";
        }else{
            $joins[]="JOIN $table $a ON $a.$qStart=$prevEndpointExpr";
        }
        $prevEndpointExpr="$a.$qEnd";$endExpr=$prevEndpointExpr;
        $select[]="$a.$qEnd AS n".($i+1)."_id";
        if(!empty($sp['pk']))$select[]="$a.".pf_qi($sp['pk'])." AS e{$i}_pk";
        foreach($sp['meta'] as $key=>$col)$select[]="$a.".pf_qi($col)." AS ".pf_qi("e{$i}_{$key}");
        if(!empty($sp['condition'])){
            if($sp['condition']==='direct_disease_drug_evidence=0'){
                $where[]="$a.`direct_disease_drug_evidence`=0";
            }
        }
    }
    $where[]="$startExpr=:from_id";$where[]="$endExpr=:to_id";
    $sql="SELECT DISTINCT ".implode(',',$select)." FROM $from ".implode(' ',$joins)." WHERE ".implode(' AND ',$where)." LIMIT ".(int)$limit;
    $q=$pdo->prepare($sql);$q->execute($params);
    return $q->fetchAll(PDO::FETCH_ASSOC);
}
function pf_classify(array $relationNames,array $types): array {
    $len=count($relationNames);
    $from=$types[0];$to=$types[count($types)-1];
    $endpointPair=[$from,$to];sort($endpointPair);
    if($len===1&&$relationNames[0]==='direct_disease_drug'&&$endpointPair===['disease','drug'])
        return ['direct','DIRECT THERAPEUTIC EVIDENCE','Direct disease-specific disease–drug evidence.'];

    if(in_array('target_overlap_only',$relationNames,true))
        return ['target_overlap','TARGET-OVERLAP DISCOVERY','Discovery-only target overlap; not direct therapeutic evidence.'];

    for($i=0;$i<$len-1;$i++){
        $pair=[$relationNames[$i],$relationNames[$i+1]];sort($pair);
        if($pair===['disease_gene','drug_target'])
            return ['target_overlap','TARGET-OVERLAP DISCOVERY','Disease–gene plus drug–target connectivity is mechanistic discovery context and is not automatically therapeutic evidence.'];
        if($pair===['disease_trial','drug_trial'])
            return ['clinical','CLINICAL CO-OCCURRENCE','Disease and drug are connected through the same clinical trial; investigation does not establish approval or efficacy.'];
        if($pair===['disease_report','drug_report'])
            return ['clinical','CLINICAL CO-OCCURRENCE','Disease and drug are connected through the same clinical report; no disease×drug treatment assertion is inferred.'];
    }
    if(in_array('disease_trial',$relationNames,true)||in_array('drug_trial',$relationNames,true)||
       in_array('disease_report',$relationNames,true)||in_array('drug_report',$relationNames,true))
        return ['clinical','CLINICAL CO-OCCURRENCE','Clinical entities are retained as intermediary context; co-occurrence is not direct therapeutic evidence.'];

    return ['supported','EVIDENCE-SUPPORTED PATH','Path composed of explicit ODDB relationships; interpret each edge according to its own evidence semantics.'];
}
function pf_edge_id(array $sp,array $row,int $i,string $leftId,string $rightId): string {
    $pk=$row["e{$i}_pk"]??null;
    return $sp['prefix'].'::'.($pk!==null&&$pk!==''?$pk:$leftId.'::'.$rightId);
}
function pf_edge_type(string $name): string {
    return $name;
}
function pf_edge_explanation(string $name): string {
    return match($name){
      'disease_gene'=>'Explicit disease–gene association recorded in ODDB.',
      'disease_variant'=>'Explicit disease–variant association recorded in ODDB.',
      'gene_variant'=>'Gene–variant relationship recorded in ODDB.',
      'direct_disease_drug'=>'Direct disease-specific therapeutic evidence recorded in ODDB.',
      'drug_target'=>'Drug–target molecular pharmacology relationship.',
      'target_overlap_only'=>'Disease–drug discovery connection based on target overlap only.',
      'disease_trial'=>'Disease is linked to this clinical trial.',
      'drug_trial'=>'Drug is investigated in this clinical trial.',
      'disease_report'=>'Disease is linked to this clinical report.',
      'drug_report'=>'Drug is linked to this clinical report.',
      default=>'Explicit ODDB relationship.'
    };
}

$allowedTypes=['disease','gene','variant','drug'];
$fromType=qparam('from_type');$fromId=qparam('from_id');
$toType=qparam('to_type');$toId=qparam('to_id');
$maxLen=int_param('max_length',3,1,4);
$maxPaths=int_param('max_paths',10,1,15);

if(!in_array($fromType,$allowedTypes,true)||!in_array($toType,$allowedTypes,true))api_error('Path Finder endpoints must be Disease, Gene, Variant or Drug.');
if(!pf_valid_id($fromId)||!pf_valid_id($toId))api_error('Invalid Path Finder entity identifier.');
if($fromType===$toType&&$fromId===$toId)api_error('Choose two different entities.');

$rs=pf_report_schema($pdo);
$cache=[];
$fromEntity=pf_entity($pdo,$fromType,$fromId,$rs,$cache);
$toEntity=pf_entity($pdo,$toType,$toId,$rs,$cache);
if($fromEntity['label']===$fromId){
    // IDs may legitimately be labels, so do not reject solely on this condition.
}
$specs=pf_specs($pdo);
$routes=pf_routes($specs,$fromType,$toType,$maxLen);

$paths=[];$seen=[];
foreach($routes as $route){
    if(count($paths)>=$maxPaths)break;
    try{
        $rows=pf_query_route($pdo,$route,$specs,$fromId,$toId,4);
    }catch(Throwable $e){
        continue;
    }
    foreach($rows as $row){
        $types=$route['types'];$steps=$route['steps'];
        $nodeIds=[$fromId];
        foreach($steps as $i=>$step)$nodeIds[]=(string)$row['n'.($i+1).'_id'];

        // Reject repeated exact entities; a useful path should not loop through the same entity.
        $entityKeys=[];$loop=false;
        foreach($nodeIds as $i=>$nid){
            $k=$types[$i].'::'.$nid;
            if(isset($entityKeys[$k])){$loop=true;break;}
            $entityKeys[$k]=1;
        }
        if($loop)continue;

        $nodeObjs=[];$elements=[];$edgeObjs=[];$relationNames=[];
        foreach($nodeIds as $i=>$nid){
            $ent=pf_entity($pdo,$types[$i],$nid,$rs,$cache);
            $nodeObjs[]=$ent;
            $elements[]=['data'=>[
              'id'=>$ent['type'].'::'.$ent['id'],'entity_id'=>$ent['id'],'label'=>$ent['label'],'type'=>$ent['type'],
              'subtitle'=>$ent['subtitle'],'expanded'=>1,'pathfinder'=>1
            ]];
        }
        foreach($steps as $i=>$step){
            $name=$step['name'];$sp=$specs[$name];$relationNames[]=$name;
            $plus=$step['orientation']==='+';
            $travA=$nodeIds[$i];$travB=$nodeIds[$i+1];
            $leftId=$plus?$travA:$travB;$rightId=$plus?$travB:$travA;
            $meta=[];
            foreach($sp['meta'] as $key=>$col){
                $v=$row["e{$i}_{$key}"]??null;
                if($v!==null&&$v!=='')$meta[$key]=$v;
            }
            $edgeId=pf_edge_id($sp,$row,$i,$leftId,$rightId);
            $edata=[
              'id'=>$edgeId,'source'=>$sp['left_type'].'::'.$leftId,'target'=>$sp['right_type'].'::'.$rightId,
              'type'=>pf_edge_type($name),'label'=>$sp['label'],'pathfinder'=>1
            ];
            foreach($meta as $k=>$v)$edata[$k]=$v;
            if($sp['warning'])$edata['warning']=$sp['warning'];
            $elements[]=['data'=>$edata];
            $edgeObjs[]=[
              'type'=>$name,'label'=>$sp['label'],'semantic_label'=>$sp['semantic'],
              'explanation'=>pf_edge_explanation($name),'metadata'=>$meta,'warning'=>$sp['warning']
            ];
        }
        [$class,$classLabel,$warning]=pf_classify($relationNames,$types);
        $key=implode('>',array_map(static fn($n)=>$n['type'].'::'.$n['id'],$nodeObjs)).'|'.implode('>',$relationNames);
        if(isset($seen[$key]))continue;$seen[$key]=1;
        $paths[]=[
          'length'=>count($steps),'classification'=>$class,'classification_label'=>$classLabel,'warning'=>$warning,
          'nodes'=>$nodeObjs,'edges'=>$edgeObjs,'elements'=>$elements,'route'=>$relationNames,'score'=>$route['score']
        ];
        if(count($paths)>=$maxPaths)break 2;
    }
}
$rank=['direct'=>0,'supported'=>1,'target_overlap'=>2,'clinical'=>3];
usort($paths,static function($a,$b)use($rank){
    return ($a['length']<=>$b['length'])
      ?: (($rank[$a['classification']]??9)<=>($rank[$b['classification']]??9))
      ?: (($a['score']??999)<=>($b['score']??999));
});
$paths=array_slice($paths,0,$maxPaths);

json_response([
 'ok'=>true,'from'=>$fromEntity,'to'=>$toEntity,'max_length'=>$maxLen,'paths'=>$paths,
 'searched_route_templates'=>count($routes),
 'semantics'=>[
  'shortest_first'=>'Results are ordered by path length first, then by evidence interpretation priority.',
  'direct'=>'DIRECT THERAPEUTIC EVIDENCE is used only for a one-edge disease–drug association.',
  'target_overlap'=>'Disease–gene plus drug–target connectivity and target-overlap summary edges are discovery relationships, not treatment assertions.',
  'clinical'=>'Disease→Trial/Report→Drug paths represent clinical co-occurrence and do not establish approval, efficacy or a direct treatment relationship.',
  'variant'=>'A disease–variant edge is used only when an explicit disease_variant_association row exists. Indirect Disease→Gene→Variant paths remain indirect.'
 ]
]);
