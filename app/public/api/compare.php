<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';

$pdo=oddb_db();

function cmp_parse_ids(string $raw,int $max=5): array {
    $out=[];
    foreach(array_values(array_unique(array_filter(array_map('trim',explode(',',$raw))))) as $id){
        if(!preg_match('/^[A-Za-z0-9:._-]+$/',$id)) continue;
        $out[]=$id;
        if(count($out)>=$max) break;
    }
    return $out;
}
function cmp_in(array $values,string $prefix,array &$params): string {
    $m=[];
    foreach(array_values($values) as $i=>$v){
        $k=':'.$prefix.$i;$m[]=$k;$params[$k]=$v;
    }
    return $m?implode(',',$m):"''";
}
function cmp_table_exists(PDO $pdo,string $table): bool {
    $s=$pdo->prepare("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=:t");
    $s->execute([':t'=>$table]);
    return (int)$s->fetchColumn()>0;
}
function cmp_columns(PDO $pdo,string $table): array {
    $s=$pdo->prepare("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=:t");
    $s->execute([':t'=>$table]);
    return array_map(static fn($r)=>$r['column_name'],$s->fetchAll(PDO::FETCH_ASSOC));
}
function cmp_first(array $cols,array $names): ?string {
    foreach($names as $n) if(in_array($n,$cols,true)) return $n;
    return null;
}
function cmp_qi(string $id): string {
    return '`'.str_replace('`','``',$id).'`';
}
function cmp_report_schema(PDO $pdo): ?array {
    $rt=null;
    foreach(['clinical_report','clinical_reports'] as $t){if(cmp_table_exists($pdo,$t)){$rt=$t;break;}}
    if(!$rt)return null;
    $rc=cmp_columns($pdo,$rt);
    $rid=cmp_first($rc,['clinical_report_id','report_id','id']);
    if(!$rid)return null;
    $label=cmp_first($rc,['title','report_title','name','source_title','source_id',$rid])??$rid;
    $da=null;
    foreach(['disease_clinical_report_association','disease_clinical_report','disease_report_association'] as $t){if(cmp_table_exists($pdo,$t)){$da=$t;break;}}
    $drc=$da?cmp_first(cmp_columns($pdo,$da),['clinical_report_id','report_id']):null;
    return ['table'=>$rt,'id'=>$rid,'label'=>$label,'disease_assoc'=>$da,'disease_report_col'=>$drc];
}
function cmp_group_rows(array $rows,string $idKey,string $labelKey,string $type,array $diseaseNames): array {
    $g=[];
    foreach($rows as $r){
        $id=(string)$r[$idKey];
        if(!isset($g[$id]))$g[$id]=['type'=>$type,'id'=>$id,'label'=>(string)$r[$labelKey],'diseases'=>[],'disease_count'=>0];
        $did=(string)$r['disease_id'];
        $g[$id]['diseases'][$did]=['disease_id'=>$did,'disease_name'=>$diseaseNames[$did]??$did];
    }
    foreach($g as &$x){$x['diseases']=array_values($x['diseases']);$x['disease_count']=count($x['diseases']);}
    unset($x);
    return array_values($g);
}
function cmp_split(array $grouped,array $diseaseNames): array {
    $shared=[];$unique=[];
    foreach($grouped as $x){
        if($x['disease_count']>=2)$shared[]=$x;
        elseif($x['disease_count']===1){
            $did=$x['diseases'][0]['disease_id'];
            $x['owner_disease_id']=$did;
            $x['owner_disease_name']=$diseaseNames[$did]??$did;
            $unique[]=$x;
        }
    }
    usort($shared,static fn($a,$b)=>($b['disease_count']<=>$a['disease_count'])?:strcasecmp($a['label'],$b['label']));
    usort($unique,static fn($a,$b)=>strcasecmp($a['owner_disease_name'],$b['owner_disease_name'])?:strcasecmp($a['label'],$b['label']));
    return [$shared,$unique];
}

$ids=cmp_parse_ids(qparam('disease_ids'),5);
if(count($ids)<2)api_error('Select at least 2 diseases for comparison.');
if(count($ids)>5)api_error('Disease comparison is limited to 5 diseases.');

$p=[];$din=cmp_in($ids,'d',$p);
$s=$pdo->prepare("SELECT disease_id,disease_name FROM disease WHERE disease_id IN ($din) ORDER BY disease_name");
$s->execute($p);
$diseases=$s->fetchAll(PDO::FETCH_ASSOC);
if(count($diseases)!==count($ids))api_error('One or more selected disease IDs were not found.');
$diseaseNames=[];
foreach($diseases as $d)$diseaseNames[$d['disease_id']]=$d['disease_name'];

$results=[
 'shared_genes'=>[],'unique_genes'=>[],
 'shared_variants'=>[],'unique_variants'=>[],
 'shared_direct_drugs'=>[],'unique_direct_drugs'=>[],
 'shared_overlap_drugs'=>[],
 'shared_trials'=>[],'shared_reports'=>[],
 'shared_target_drugs'=>[]
];

/* Genes: actual DGA rows only. */
$p=[];$din=cmp_in($ids,'gdis',$p);
$s=$pdo->prepare("SELECT DISTINCT a.disease_id,g.hgnc_id,g.gene_symbol
 FROM disease_gene_association a JOIN gene g ON g.hgnc_id=a.hgnc_id
 WHERE a.disease_id IN ($din)");
$s->execute($p);
[$results['shared_genes'],$results['unique_genes']]=cmp_split(
 cmp_group_rows($s->fetchAll(PDO::FETCH_ASSOC),'hgnc_id','gene_symbol','gene',$diseaseNames),$diseaseNames
);

/* Variants: explicit DVA only; never inferred through a gene. */
$p=[];$din=cmp_in($ids,'vdis',$p);
$s=$pdo->prepare("SELECT DISTINCT a.disease_id,v.variant_id,
 COALESCE(NULLIF(v.clinvar_variation_id,''),NULLIF(v.variant_name,''),v.variant_id) variant_label
 FROM disease_variant_association a JOIN variant v ON v.variant_id=a.variant_id
 WHERE a.disease_id IN ($din)");
$s->execute($p);
[$results['shared_variants'],$results['unique_variants']]=cmp_split(
 cmp_group_rows($s->fetchAll(PDO::FETCH_ASSOC),'variant_id','variant_label','variant',$diseaseNames),$diseaseNames
);

/* Direct therapeutic evidence only. */
$p=[];$din=cmp_in($ids,'ddis',$p);
$s=$pdo->prepare("SELECT DISTINCT a.disease_id,dr.drug_id,dr.preferred_name
 FROM disease_drug_association a JOIN drug dr ON dr.drug_id=a.drug_id
 WHERE a.disease_id IN ($din)");
$s->execute($p);
[$results['shared_direct_drugs'],$results['unique_direct_drugs']]=cmp_split(
 cmp_group_rows($s->fetchAll(PDO::FETCH_ASSOC),'drug_id','preferred_name','drug',$diseaseNames),$diseaseNames
);

/* Target-overlap discovery only; kept separate from direct DDA. */
$p=[];$din=cmp_in($ids,'odis',$p);
$s=$pdo->prepare("SELECT DISTINCT x.disease_id,dr.drug_id,dr.preferred_name
 FROM disease_drug_target_overlap_summary x JOIN drug dr ON dr.drug_id=x.drug_id
 WHERE x.direct_disease_drug_evidence=0 AND x.disease_id IN ($din)");
$s->execute($p);
$ov=cmp_group_rows($s->fetchAll(PDO::FETCH_ASSOC),'drug_id','preferred_name','drug',$diseaseNames);
foreach($ov as &$x)$x['discovery_only']=true;
unset($x);
[$results['shared_overlap_drugs'],$_unused]=cmp_split($ov,$diseaseNames);

/* Shared clinical trials are trial entities, not inferred disease-drug pairs. */
$p=[];$din=cmp_in($ids,'tdis',$p);
$s=$pdo->prepare("SELECT DISTINCT a.disease_id,t.clinical_trial_id,
 COALESCE(NULLIF(t.nct_id,''),NULLIF(t.title,''),t.clinical_trial_id) trial_label
 FROM disease_clinical_trial_association a
 JOIN clinical_trial t ON t.clinical_trial_id=a.clinical_trial_id
 WHERE a.disease_id IN ($din)");
$s->execute($p);
$tr=cmp_group_rows($s->fetchAll(PDO::FETCH_ASSOC),'clinical_trial_id','trial_label','trial',$diseaseNames);
[$results['shared_trials'],$_unused]=cmp_split($tr,$diseaseNames);

/* Shared clinical reports are preserved as report entities; no disease×drug cross-product. */
$rs=cmp_report_schema($pdo);
if($rs&&$rs['disease_assoc']&&$rs['disease_report_col']){
    $rt=cmp_qi($rs['table']);$rid=cmp_qi($rs['id']);$rl=cmp_qi($rs['label']);
    $at=cmp_qi($rs['disease_assoc']);$arc=cmp_qi($rs['disease_report_col']);
    $p=[];$din=cmp_in($ids,'rdis',$p);
    $sql="SELECT DISTINCT a.disease_id,r.$rid report_id,r.$rl report_label
          FROM $at a JOIN $rt r ON r.$rid=a.$arc WHERE a.disease_id IN ($din)";
    $s=$pdo->prepare($sql);$s->execute($p);
    $rr=cmp_group_rows($s->fetchAll(PDO::FETCH_ASSOC),'report_id','report_label','report',$diseaseNames);
    [$results['shared_reports'],$_unused]=cmp_split($rr,$diseaseNames);
}

/* Shared-neighbor discovery: drugs targeting >=2 distinct genes present in the selected diseases.
   This is molecular target connectivity, not disease-specific therapeutic evidence. */
$p=[];$din=cmp_in($ids,'sgd',$p);
$sql="SELECT dr.drug_id,dr.preferred_name,
             COUNT(DISTINCT dga.hgnc_id) target_gene_count,
             GROUP_CONCAT(DISTINCT g.gene_symbol ORDER BY g.gene_symbol SEPARATOR ', ') target_genes,
             COUNT(DISTINCT dga.disease_id) disease_count
      FROM disease_gene_association dga
      JOIN gene g ON g.hgnc_id=dga.hgnc_id
      JOIN drug_target_association dta ON dta.hgnc_id=dga.hgnc_id
      JOIN drug dr ON dr.drug_id=dta.drug_id
      WHERE dga.disease_id IN ($din)
      GROUP BY dr.drug_id,dr.preferred_name
      HAVING COUNT(DISTINCT dga.hgnc_id)>=2
      ORDER BY target_gene_count DESC,disease_count DESC,dr.preferred_name
      LIMIT 100";
$s=$pdo->prepare($sql);$s->execute($p);
foreach($s->fetchAll(PDO::FETCH_ASSOC) as $r){
    $results['shared_target_drugs'][]=[
      'type'=>'drug','id'=>(string)$r['drug_id'],'label'=>(string)$r['preferred_name'],
      'target_gene_count'=>(int)$r['target_gene_count'],'target_genes'=>$r['target_genes'],
      'disease_count'=>(int)$r['disease_count'],'discovery_only'=>true,'diseases'=>[]
    ];
}

json_response([
 'ok'=>true,
 'diseases'=>$diseases,
 'results'=>$results,
 'summary'=>[
   'shared_genes'=>count($results['shared_genes']),
   'shared_variants'=>count($results['shared_variants']),
   'shared_direct_drugs'=>count($results['shared_direct_drugs']),
   'shared_overlap_drugs'=>count($results['shared_overlap_drugs']),
   'shared_trials'=>count($results['shared_trials']),
   'shared_reports'=>count($results['shared_reports']),
   'shared_target_drugs'=>count($results['shared_target_drugs'])
 ],
 'semantics'=>[
   'shared_definition'=>'An entity linked to at least two selected diseases.',
   'variant_rule'=>'Variants are compared only through explicit disease_variant_association rows.',
   'direct_drug_rule'=>'Direct therapeutic evidence comes only from disease_drug_association.',
   'target_overlap_rule'=>'Target-overlap results are discovery relationships and are not direct therapeutic evidence.',
   'clinical_rule'=>'Trials and reports remain intermediary evidence entities; no disease×drug cross-products are created.'
 ]
]);
