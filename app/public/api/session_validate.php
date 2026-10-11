<?php
/* ODDB v1 analysis validation v0.7.6. Read-only: no imported evidence is trusted. */
declare(strict_types=1);
require_once __DIR__.'/db.php';

function sv_q(string $s): string {
    if (!preg_match('/^[A-Za-z0-9_]+$/', $s)) throw new RuntimeException('Invalid identifier.');
    return '`'.$s.'`';
}
function sv_columns(PDO $db, string $table): array {
    static $cache=[];
    if (!array_key_exists($table, $cache)) {
        $s=$db->prepare('SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=:t ORDER BY ordinal_position');
        $s->execute([':t'=>$table]);
        $cache[$table]=array_column($s->fetchAll(PDO::FETCH_ASSOC), 'column_name');
    }
    return $cache[$table];
}
function sv_first(array $columns, array $names): ?string {
    foreach ($names as $name) if (in_array($name,$columns,true)) return $name;
    return null;
}
function sv_table(PDO $db, array $names): ?string {
    foreach ($names as $name) if (sv_columns($db,$name)) return $name;
    return null;
}
function sv_meta(): array {
    $release=getenv('ODDB_DATA_RELEASE') ?: null;
    $source=$release ? 'server environment' : null;
    $file=dirname(__DIR__,2).'/config/analysis_release.json';
    if (!$release && is_file($file)) {
        $data=json_decode((string)file_get_contents($file),true);
        if (is_array($data) && is_string($data['release_id']??null) && trim($data['release_id'])!=='') {
            $release=trim($data['release_id']); $source='application configuration';
        }
    }
    return ['release_id'=>$release,'release_source'=>$source,'release_status'=>$release?'declared':'unknown',
            'validated_at'=>gmdate('c'),'app_version'=>'0.7.8'];
}
function sv_node_specs(PDO $db): array {
    $specs=[
        'disease'=>['disease','disease_id',['disease_name'],['localization']],
        'gene'=>['gene','hgnc_id',['gene_symbol'],['gene_name']],
        'variant'=>['variant','variant_id',['clinvar_variation_id','variant_name','rsid','rs_id'],['clinical_significance']],
        'drug'=>['drug','drug_id',['preferred_name'],['maximum_clinical_stage']],
        'trial'=>['clinical_trial','clinical_trial_id',['nct_id','title'],['phase','overall_status']],
        'locus'=>['locus','locus_id',['locus_label'],[]],
        'consequence'=>['variant_consequence_category','consequence_id',['consequence_term'],[]]
    ];
    $report=sv_table($db,['clinical_report','clinical_reports']);
    if ($report) {
        $columns=sv_columns($db,$report);
        $id=sv_first($columns,['clinical_report_id','report_id','id']);
        if ($id) $specs['report']=[$report,$id,['title','report_title','name','source_title','source_id'],['report_type','source','journal','status']];
    }
    return $specs;
}
function sv_edge_specs(PDO $db): array {
    // table, source type/column, target type/column, primary key, canonical prefix.
    $s=[
        'disease_gene'=>['disease_gene_association','disease','disease_id','gene','hgnc_id','association_id','dga'],
        'disease_locus'=>['disease_locus_association','disease','disease_id','locus','locus_id','association_id','dla'],
        'disease_variant'=>['disease_variant_association','disease','disease_id','variant','variant_id',null,'dva'],
        'gene_variant'=>['gene_variant_association','gene','hgnc_id','variant','variant_id',null,'gva'],
        'variant_consequence'=>['variant_consequence','variant','variant_id','consequence','consequence_id',null,'vc'],
        'direct_disease_drug'=>['disease_drug_association','disease','disease_id','drug','drug_id','disease_drug_association_id','dda'],
        'drug_target'=>['drug_target_association','drug','drug_id','gene','hgnc_id','drug_target_association_id','dta'],
        'target_overlap_only'=>['disease_drug_target_overlap_summary','disease','disease_id','drug','drug_id','summary_id','overlap'],
        'disease_trial'=>['disease_clinical_trial_association','disease','disease_id','trial','clinical_trial_id',null,'dtrial'],
        'drug_trial'=>['drug_clinical_trial_association','drug','drug_id','trial','clinical_trial_id',null,'drtrial']
    ];
    foreach (['disease','drug'] as $type) {
        $table=sv_table($db,[$type.'_clinical_report_association',$type.'_clinical_report',$type.'_report_association']);
        if (!$table) continue;
        $column=sv_first(sv_columns($db,$table),['clinical_report_id','report_id']);
        if ($column) $s[$type.'_report']=[$table,$type,$type.'_id','report',$column,null,$type==='disease'?'dreport':'drreport'];
    }
    return $s;
}
function sv_clean_id($id): bool {
    return is_string($id) && strlen($id)<=180 && (bool)preg_match('/^[A-Za-z0-9:._-]+$/',$id);
}
function sv_sort($value) {
    if (!is_array($value)) return $value;
    if (!array_is_list($value)) ksort($value,SORT_STRING);
    foreach ($value as $k=>$v) $value[$k]=sv_sort($v);
    return $value;
}
function sv_issue(string $kind, string $id, string $status, string $reason): array {
    return ['kind'=>$kind,'id'=>$id,'status'=>$status,'reason'=>$reason];
}
function sv_public_row(array $row): array {
    $keys=['inheritance','evidence_class','evidence_status','source','source_id','pmid','doi','mapping_method',
           'association_class','evidence_strength_class','action_type','mechanism_of_action','target_gene_count',
           'target_genes','identity_resolution_status','source_value'];
    $out=[];
    foreach ($keys as $key) if (array_key_exists($key,$row)) $out[$key]=$row[$key];
    if (isset($row['source'])) $out['source_name']=$row['source'];
    return $out;
}

$method=$_SERVER['REQUEST_METHOD']??'GET';
if ($method==='GET') json_response(['ok'=>true,'metadata'=>sv_meta()]);
if ($method!=='POST') api_error('Use POST to validate an analysis.',405);
$input=file_get_contents('php://input',false,null,0,16777217);
if ($input===false || strlen($input)>16777216) api_error('Analysis validation request exceeds 16 MiB.',413);
try { $payload=json_decode($input,true,64,JSON_THROW_ON_ERROR); }
catch (JsonException $e) { api_error('The analysis contains invalid JSON.'); }
if (!is_array($payload) || !is_array($payload['nodes']??null) || !is_array($payload['edges']??null)) api_error('Nodes and edges must be arrays.');
if (!array_is_list($payload['nodes']) || !array_is_list($payload['edges'])) api_error('Nodes and edges must be lists.');
if (count($payload['nodes'])>5000 || count($payload['edges'])>15000) api_error('This analysis exceeds the limit of 5,000 entities or 15,000 relationships.',413);
$db=oddb_db(); $nodeSpecs=sv_node_specs($db); $edgeSpecs=sv_edge_specs($db);
$issues=[]; $requested=[]; $groups=[]; $nodes=[]; $edges=[];
$db->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
$db->exec('SET TRANSACTION READ ONLY');
$db->beginTransaction();
foreach ($payload['nodes'] as $item) {
    if (!is_array($item) || !is_string($item['type']??null) || !sv_clean_id($item['entity_id']??null)) api_error('Invalid entity reference.');
    $type=$item['type']; $id=$item['entity_id']; $key=$type.'::'.$id;
    if (isset($requested[$key])) api_error('Duplicate entity reference.');
    $requested[$key]=['type'=>$type,'entity_id'=>$id];
    if (!isset($nodeSpecs[$type])) {$issues[]=sv_issue('node',$key,'unverified','Entity type or schema is unavailable.');continue;}
    [$table,$column]=$nodeSpecs[$type];
    if (!in_array($column,sv_columns($db,$table),true)) {$issues[]=sv_issue('node',$key,'unverified','Entity table or identifier column is unavailable.');continue;}
    $groups[$type][]=$id;
}
foreach ($groups as $type=>$ids) {
    [$table,$idColumn,$labels,$subtitles]=$nodeSpecs[$type];
    $columns=sv_columns($db,$table);
    $fields=array_values(array_unique(array_merge([$idColumn],array_intersect(array_merge($labels,$subtitles,['title','phase','overall_status']),$columns))));
    foreach (array_chunk($ids,300) as $chunk) {
        $sql='SELECT '.implode(',',array_map('sv_q',$fields)).' FROM '.sv_q($table).' WHERE '.sv_q($idColumn).' IN ('.implode(',',array_fill(0,count($chunk),'?')).')';
        $q=$db->prepare($sql);$q->execute($chunk);
        foreach ($q->fetchAll(PDO::FETCH_ASSOC) as $row) {
            $id=(string)$row[$idColumn]; $key=$type.'::'.$id; $label=$id; $subtitle='';
            foreach ($labels as $column) if (isset($row[$column]) && trim((string)$row[$column])!=='') {$label=(string)$row[$column];break;}
            foreach ($subtitles as $column) if (isset($row[$column]) && trim((string)$row[$column])!=='') {$subtitle=(string)$row[$column];break;}
            $nodes[$key]=['id'=>$key,'type'=>$type,'entity_id'=>$id,'label'=>$label,'subtitle'=>$subtitle];
            foreach (['title','phase','overall_status'] as $column) if (isset($row[$column])) $nodes[$key][$column]=$row[$column];
        }
    }
    foreach ($ids as $id) if (!isset($nodes[$type.'::'.$id])) $issues[]=sv_issue('node',$type.'::'.$id,'missing','Entity is not present in the current database.');
}
$edgeGroups=[]; $edgeSeen=[];
foreach ($payload['edges'] as $edge) {
    if (!is_array($edge) || !sv_clean_id($edge['id']??null) || !is_string($edge['type']??null) || !is_string($edge['source']??null) || !is_string($edge['target']??null)) api_error('Invalid relationship reference.');
    $id=$edge['id'];$type=$edge['type'];
    if (isset($edgeSeen[$id])) api_error('Duplicate relationship reference.');
    $edgeSeen[$id]=true;
    if (!isset($edgeSpecs[$type])) {$issues[]=sv_issue('edge',$id,'unverified','Relationship type or schema is unavailable.');continue;}
    if (!isset($nodes[$edge['source']],$nodes[$edge['target']])) {$issues[]=sv_issue('edge',$id,'missing','One or both endpoint entities could not be validated.');continue;}
    [$table,$leftType,$leftCol,$rightType,$rightCol,$pk,$prefix]=$edgeSpecs[$type];
    $columns=sv_columns($db,$table);
    $required=[$leftCol,$rightCol];if($pk)$required[]=$pk;
    if ($type==='target_overlap_only')$required[]='direct_disease_drug_evidence';
    if (array_diff($required,$columns)) {$issues[]=sv_issue('edge',$id,'unverified','Relationship table or required columns are unavailable.');continue;}
    $a=$nodes[$edge['source']];$b=$nodes[$edge['target']];
    if ($a['type']!==$leftType || $b['type']!==$rightType) {$issues[]=sv_issue('edge',$id,'invalid','Relationship endpoints do not match its evidence type.');continue;}
    $prefixText=$prefix.'::';
    if (strncmp($id,$prefixText,strlen($prefixText))!==0 || (!$pk && $id!==$prefixText.$a['entity_id'].'::'.$b['entity_id'])) {$issues[]=sv_issue('edge',$id,'invalid','Relationship identifier does not match its endpoints.');continue;}
    $edge['_left']=$a['entity_id'];$edge['_right']=$b['entity_id'];$edge['_pk']=$pk?substr($id,strlen($prefixText)):null;
    if ($pk && !sv_clean_id($edge['_pk'])) {$issues[]=sv_issue('edge',$id,'invalid','Invalid relationship record identifier.');continue;}
    $edgeGroups[$type][]=$edge;
}
$metadataKeys=['inheritance','evidence_class','evidence_status','source','source_id','pmid','doi','mapping_method','association_class','evidence_strength_class','action_type','mechanism_of_action','target_gene_count','target_genes','identity_resolution_status','source_value'];
foreach ($edgeGroups as $type=>$group) {
    [$table,$leftType,$leftCol,$rightType,$rightCol,$pk,$prefix]=$edgeSpecs[$type];
    $columns=sv_columns($db,$table);
    $select=array_values(array_unique(array_merge([$leftCol,$rightCol],$pk?[$pk]:[],array_intersect($metadataKeys,$columns))));
    foreach (array_chunk($group,75) as $chunk) {
        $terms=[];$params=[];
        foreach ($chunk as $edge) {
            $term=sv_q($leftCol).'=? AND '.sv_q($rightCol).'=?';$params[]=$edge['_left'];$params[]=$edge['_right'];
            if ($pk) {$term.=' AND '.sv_q($pk).'=?';$params[]=$edge['_pk'];}
            $terms[]='('.$term.')';
        }
        $sql='SELECT '.implode(',',array_map('sv_q',$select)).' FROM '.sv_q($table).' WHERE ('.implode(' OR ',$terms).')';
        if ($type==='target_overlap_only')$sql.=' AND `direct_disease_drug_evidence`=0';
        $q=$db->prepare($sql);$q->execute($params);$found=[];
        foreach ($q->fetchAll(PDO::FETCH_ASSOC) as $row) {
            $id=$prefix.'::'.($pk?(string)$row[$pk]:(string)$row[$leftCol].'::'.(string)$row[$rightCol]);
            // Pair-based relationships may have multiple provenance rows. Keep all in stable order.
            $found[$id][]=$row;
        }
        foreach ($chunk as $edge) {
            $id=$edge['id'];
            if (!isset($found[$id])) {$issues[]=sv_issue('edge',$id,'missing','Relationship record is absent or no longer has the saved evidence semantics.');continue;}
            $rows=$found[$id];usort($rows,static fn($a,$b)=>strcmp(json_encode(sv_sort($a)),json_encode(sv_sort($b))));
            $data=array_merge(sv_public_row($rows[0]),['id'=>$id,'type'=>$type,'source'=>$edge['source'],'target'=>$edge['target']]);
            $data['label']=match($type) {
                'disease_gene'=>($data['inheritance']??'')?:'disease–gene',
                'disease_locus'=>'disease–locus',
                'disease_variant'=>($data['mapping_method']??'')?:'explicit disease–variant',
                'gene_variant'=>'gene–variant','variant_consequence'=>'variant consequence',
                'direct_disease_drug'=>($data['evidence_strength_class']??'')?:'direct evidence',
                'drug_target'=>($data['action_type']??'')?:'target',
                'target_overlap_only'=>'target overlap',
                'disease_trial'=>'clinical trial association','drug_trial'=>'investigated drug',
                default=>'clinical report association'
            };
            if (count($rows)>1) $data['provenance_rows']=array_map('sv_public_row',$rows);
            if ($type==='target_overlap_only')$data['warning']='Discovery connection only; not direct therapeutic evidence.';
            if (in_array($type,['disease_trial','drug_trial'],true))$data['warning']='Clinical trial investigation does not by itself establish approval or efficacy.';
            if (in_array($type,['disease_report','drug_report'],true))$data['warning']='Report co-occurrence is preserved through the report entity; it is not an inferred disease–drug treatment pair.';
            if ($type==='direct_disease_drug')$data['clinical_stage']=$nodes[$edge['target']]['subtitle']??'';
            if (in_array($type,['disease_trial','drug_trial'],true))foreach(['phase','overall_status'] as $column)if(isset($nodes[$edge['target']][$column]))$data[$column]=$nodes[$edge['target']][$column];
            $edges[$id]=$data;
        }
    }
}
// Include the current primary evidence records behind direct therapeutic edges.
$evidenceColumns=sv_columns($db,'disease_drug_evidence');
if (in_array('disease_drug_association_id',$evidenceColumns,true)) {
    $dda=array_filter($edges,static fn($e)=>$e['type']==='direct_disease_drug');
    $fields=array_intersect(['disease_drug_association_id','evidence_subtype','source','source_id','pmid','doi','evidence_class','evidence_status','evidence_strength_class'],$evidenceColumns);
    foreach (array_chunk(array_keys($dda),300) as $chunk) {
        $ids=array_map(static fn($id)=>substr($id,5),$chunk);
        $q=$db->prepare('SELECT '.implode(',',array_map('sv_q',$fields)).' FROM `disease_drug_evidence` WHERE `disease_drug_association_id` IN ('.implode(',',array_fill(0,count($ids),'?')).')');$q->execute($ids);
        $rowsById=[];foreach($q->fetchAll(PDO::FETCH_ASSOC) as $row)$rowsById['dda::'.$row['disease_drug_association_id']][]=$row;
        foreach($rowsById as $id=>$rows){
            usort($rows,static fn($a,$b)=>strcmp(json_encode(sv_sort($a)),json_encode(sv_sort($b))));
            $edges[$id]['evidence_rows']=$rows;
            foreach(['evidence_subtype'=>'evidence_subtypes','source'=>'evidence_sources','source_id'=>'evidence_source_ids','pmid'=>'pmid','doi'=>'doi'] as $column=>$name) {
                $values=array_values(array_unique(array_filter(array_map(static fn($r)=>(string)($r[$column]??''),$rows),static fn($v)=>$v!=='')));
                $edges[$id][$name]=implode(' | ',$values);
            }
        }
    }
}
$db->commit();
$metadata=sv_meta();
$metadata['graph_checksum']=hash('sha256',json_encode(sv_sort(['nodes'=>$nodes,'edges'=>$edges]),JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES));
json_response(['ok'=>true,'metadata'=>$metadata,'nodes'=>array_values($nodes),'edges'=>array_values($edges),'issues'=>$issues,
               'counts'=>['nodes'=>count($nodes),'edges'=>count($edges),'rejected'=>count($issues)]]);
