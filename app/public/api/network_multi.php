<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';

$pdo = oddb_db();

function parse_ids(string $raw, int $max=30): array {
    if ($raw === '') return [];
    $parts = array_values(array_unique(array_filter(array_map('trim', explode(',', $raw)))));
    $out = [];
    foreach ($parts as $id) {
        if (!preg_match('/^[A-Za-z0-9:._-]+$/', $id)) continue;
        $out[] = $id;
        if (count($out) >= $max) break;
    }
    return $out;
}

function in_clause(array $values, string $prefix, array &$params): string {
    $marks = [];
    foreach (array_values($values) as $i => $value) {
        $key = ':'.$prefix.$i;
        $marks[] = $key;
        $params[$key] = $value;
    }
    return $marks ? implode(',', $marks) : "''";
}

function add_node(array &$nodes, string $type, string $id, string $label, array $extra=[]): void {
    if ($id === '') return;
    $key = $type.'::'.$id;
    $base = [
        'id'=>$key,
        'entity_id'=>$id,
        'label'=>$label !== '' ? $label : $id,
        'type'=>$type
    ];
    if (!isset($nodes[$key])) {
        $nodes[$key] = ['data'=>array_merge($base, $extra)];
        return;
    }
    $nodes[$key]['data'] = array_merge($nodes[$key]['data'], array_filter(
        $extra,
        static fn($v) => $v !== null && $v !== ''
    ));
}

function add_edge(array &$edges, string $id, string $source, string $target, string $type, array $extra=[]): void {
    if (isset($edges[$id])) return;
    $edges[$id] = ['data'=>array_merge(
        ['id'=>$id,'source'=>$source,'target'=>$target,'type'=>$type],
        $extra
    )];
}

$mode = qparam('mode','gene');
$gcat = qparam('gene_category_id');
$cons = qparam('consequence_id');
$phase = qparam('drug_phase');

$seedDiseases = parse_ids(qparam('disease_ids'), 20);
$selectedGenes = parse_ids(qparam('gene_ids'), 30);

$expandGeneDiseases = qparam('expand_gene_diseases','1') !== '0';
$includeNeighborGenes = qparam('include_neighbor_genes','0') === '1';

$direct = qparam('direct','1') !== '0';
$overlap = qparam('overlap','0') === '1';
$target = qparam('target','1') !== '0';
$limit = int_param('limit',600,50,1200);

if (!in_array($mode, ['gene','variant'], true)) {
    api_error('Unsupported mode.');
}
if (!$seedDiseases && !$selectedGenes) {
    api_error('At least one disease or gene must be selected.');
}

$nodes = [];
$edges = [];
$graphDiseaseIds = [];
$graphGeneIds = [];

/* Seed disease nodes are always retained in the graph. */
if ($seedDiseases) {
    $p = [];
    $in = in_clause($seedDiseases, 'sd', $p);
    $s = $pdo->prepare("SELECT disease_id,disease_name FROM disease WHERE disease_id IN ($in)");
    $s->execute($p);
    foreach ($s as $r) {
        $graphDiseaseIds[$r['disease_id']] = true;
        add_node($nodes,'disease',$r['disease_id'],$r['disease_name'],[
            'seed'=>1,
            'origin'=>'selected disease'
        ]);
    }
}

/* Explicitly selected genes are retained even if filtering removes other edges. */
if ($selectedGenes) {
    $p = [];
    $in = in_clause($selectedGenes, 'sg', $p);
    $s = $pdo->prepare("SELECT hgnc_id,gene_symbol FROM gene WHERE hgnc_id IN ($in)");
    $s->execute($p);
    foreach ($s as $r) {
        $graphGeneIds[$r['hgnc_id']] = true;
        add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol'],[
            'selected_for_expansion'=>1,
            'origin'=>'selected gene'
        ]);
    }
}

if ($mode === 'gene') {
    if ($gcat === 'GENE-02') {
        if ($seedDiseases) {
            $p = [];
            $din = in_clause($seedDiseases, 'ld', $p);
            $s = $pdo->prepare("
                SELECT a.association_id,d.disease_id,d.disease_name,l.locus_id,l.locus_label,
                       a.evidence_class,a.evidence_status,a.source,a.pmid,a.doi
                FROM disease_locus_association a
                JOIN disease d ON d.disease_id=a.disease_id
                JOIN locus l ON l.locus_id=a.locus_id
                WHERE d.disease_id IN ($din)
                ORDER BY d.disease_name,l.locus_label
                LIMIT $limit
            ");
            $s->execute($p);
            foreach ($s as $r) {
                add_node($nodes,'disease',$r['disease_id'],$r['disease_name'],['seed'=>1]);
                add_node($nodes,'locus',$r['locus_id'],$r['locus_label'],['origin'=>'selected disease']);
                add_edge($edges,'dla::'.$r['association_id'],
                    'disease::'.$r['disease_id'],'locus::'.$r['locus_id'],'disease_locus',[
                        'label'=>'disease–locus',
                        'evidence_class'=>$r['evidence_class'],
                        'evidence_status'=>$r['evidence_status'],
                        'source_name'=>$r['source'],
                        'pmid'=>$r['pmid'],
                        'doi'=>$r['doi']
                    ]);
            }
        }
    } else {
        /*
         * First pass:
         *  - all genes linked to selected diseases
         *  - all diseases linked to genes explicitly selected for expansion
         */
        $where = [];
        $p = [];

        if ($seedDiseases) {
            $din = in_clause($seedDiseases,'gd',$p);
            $where[] = "d.disease_id IN ($din)";
        }

        if ($selectedGenes && $expandGeneDiseases) {
            $gin = in_clause($selectedGenes,'gg',$p);
            $where[] = "g.hgnc_id IN ($gin)";
        }

        if ($where) {
            $extra = '';
            if ($gcat !== '') {
                $extra = " AND EXISTS(
                    SELECT 1 FROM gene_category_membership gm
                    WHERE gm.hgnc_id=g.hgnc_id
                      AND gm.gene_category_id=:gcat
                )";
                $p[':gcat'] = $gcat;
            }

            $sql = "
                SELECT a.association_id,d.disease_id,d.disease_name,g.hgnc_id,g.gene_symbol,
                       a.inheritance,a.evidence_class,a.evidence_status,a.source,a.source_id,a.pmid,a.doi
                FROM disease_gene_association a
                JOIN disease d ON d.disease_id=a.disease_id
                JOIN gene g ON g.hgnc_id=a.hgnc_id
                WHERE (".implode(' OR ', $where).") $extra
                ORDER BY d.disease_name,g.gene_symbol
                LIMIT $limit
            ";
            $s = $pdo->prepare($sql);
            $s->execute($p);

            foreach ($s as $r) {
                $isSeed = in_array($r['disease_id'],$seedDiseases,true);
                $isSelectedGene = in_array($r['hgnc_id'],$selectedGenes,true);

                $graphDiseaseIds[$r['disease_id']] = true;
                $graphGeneIds[$r['hgnc_id']] = true;

                add_node($nodes,'disease',$r['disease_id'],$r['disease_name'],[
                    'seed'=>$isSeed ? 1 : 0,
                    'expanded'=>$isSeed ? 0 : 1,
                    'origin'=>$isSeed ? 'selected disease' : 'connected through selected gene'
                ]);
                add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol'],[
                    'selected_for_expansion'=>$isSelectedGene ? 1 : 0,
                    'origin'=>$isSelectedGene ? 'selected gene' : 'disease-associated gene'
                ]);
                add_edge($edges,'dga::'.$r['association_id'],
                    'disease::'.$r['disease_id'],'gene::'.$r['hgnc_id'],'disease_gene',[
                        'label'=>$r['inheritance'] ?: 'disease–gene',
                        'source_name'=>$r['source'],
                        'source_id'=>$r['source_id'],
                        'evidence_class'=>$r['evidence_class'],
                        'evidence_status'=>$r['evidence_status'],
                        'pmid'=>$r['pmid'],
                        'doi'=>$r['doi']
                    ]);
            }
        }

        /*
         * Optional second pass:
         * Keep connected diseases in the graph AND show their other genes.
         * This is only done after expansion, avoiding an uncontrolled whole-database graph.
         */
        if ($includeNeighborGenes && $graphDiseaseIds) {
            $ids = array_keys($graphDiseaseIds);
            $p = [];
            $din = in_clause($ids,'ngd',$p);
            $extra = '';
            if ($gcat !== '') {
                $extra = " AND EXISTS(
                    SELECT 1 FROM gene_category_membership gm
                    WHERE gm.hgnc_id=g.hgnc_id
                      AND gm.gene_category_id=:ngcat
                )";
                $p[':ngcat'] = $gcat;
            }

            $s = $pdo->prepare("
                SELECT a.association_id,d.disease_id,d.disease_name,g.hgnc_id,g.gene_symbol,
                       a.inheritance,a.evidence_class,a.evidence_status,a.source,a.source_id,a.pmid,a.doi
                FROM disease_gene_association a
                JOIN disease d ON d.disease_id=a.disease_id
                JOIN gene g ON g.hgnc_id=a.hgnc_id
                WHERE d.disease_id IN ($din) $extra
                ORDER BY d.disease_name,g.gene_symbol
                LIMIT $limit
            ");
            $s->execute($p);

            foreach ($s as $r) {
                $isSeed = in_array($r['disease_id'],$seedDiseases,true);
                $isSelectedGene = in_array($r['hgnc_id'],$selectedGenes,true);

                $graphDiseaseIds[$r['disease_id']] = true;
                $graphGeneIds[$r['hgnc_id']] = true;

                add_node($nodes,'disease',$r['disease_id'],$r['disease_name'],[
                    'seed'=>$isSeed ? 1 : 0,
                    'expanded'=>$isSeed ? 0 : 1
                ]);
                add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol'],[
                    'selected_for_expansion'=>$isSelectedGene ? 1 : 0,
                    'origin'=>$isSelectedGene ? 'selected gene' : 'gene of visible disease'
                ]);
                add_edge($edges,'dga::'.$r['association_id'],
                    'disease::'.$r['disease_id'],'gene::'.$r['hgnc_id'],'disease_gene',[
                        'label'=>$r['inheritance'] ?: 'disease–gene',
                        'source_name'=>$r['source'],
                        'source_id'=>$r['source_id'],
                        'evidence_class'=>$r['evidence_class'],
                        'evidence_status'=>$r['evidence_status'],
                        'pmid'=>$r['pmid'],
                        'doi'=>$r['doi']
                    ]);
            }
        }
    }
}

if ($mode === 'variant' && $seedDiseases) {
    $p = [];
    $din = in_clause($seedDiseases,'vd',$p);
    $consSql = '';
    if ($cons !== '') {
        $consSql = " AND EXISTS(
            SELECT 1 FROM variant_consequence vc2
            WHERE vc2.variant_id=v.variant_id
              AND vc2.consequence_id=:cons
        )";
        $p[':cons'] = $cons;
    }

    $s = $pdo->prepare("
        SELECT DISTINCT
               v.variant_id,v.clinvar_variation_id,v.variant_name,v.clinical_significance,
               dva.disease_id,d.disease_name,gva.hgnc_id,g.gene_symbol,
               dva.mapping_method,dva.evidence_class
        FROM variant v
        JOIN disease_variant_association dva ON dva.variant_id=v.variant_id
        JOIN disease d ON d.disease_id=dva.disease_id
        LEFT JOIN gene_variant_association gva ON gva.variant_id=v.variant_id
        LEFT JOIN gene g ON g.hgnc_id=gva.hgnc_id
        WHERE dva.disease_id IN ($din) $consSql
        ORDER BY v.clinvar_variation_id
        LIMIT 120
    ");
    $s->execute($p);

    foreach ($s as $r) {
        $vl = $r['clinvar_variation_id'] ?: ($r['variant_name'] ?: $r['variant_id']);
        add_node($nodes,'disease',$r['disease_id'],$r['disease_name'],['seed'=>1]);
        add_node($nodes,'variant',$r['variant_id'],$vl,[
            'subtitle'=>$r['clinical_significance'],
            'origin'=>'selected disease'
        ]);
        add_edge($edges,'dva::'.$r['disease_id'].'::'.$r['variant_id'],
            'disease::'.$r['disease_id'],'variant::'.$r['variant_id'],'disease_variant',[
                'label'=>$r['mapping_method'] ?: 'disease–variant',
                'evidence_class'=>$r['evidence_class']
            ]);

        if ($r['hgnc_id']) {
            $graphGeneIds[$r['hgnc_id']] = true;
            add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol'],['origin'=>'variant-linked gene']);
            add_edge($edges,'gva::'.$r['hgnc_id'].'::'.$r['variant_id'],
                'gene::'.$r['hgnc_id'],'variant::'.$r['variant_id'],'gene_variant',[
                    'label'=>'gene–variant'
                ]);
        }
    }
}

/* Direct therapeutic evidence for all diseases currently retained in the graph. */
if ($direct && $graphDiseaseIds) {
    $ids = array_keys($graphDiseaseIds);
    $p = [];
    $din = in_clause($ids,'dd',$p);
    $phaseSql = '';
    if ($phase !== '') {
        $phaseSql = " AND dr.maximum_clinical_stage=:phase";
        $p[':phase'] = $phase;
    }

    $s = $pdo->prepare("
        SELECT a.disease_drug_association_id,d.disease_id,d.disease_name,
               dr.drug_id,dr.preferred_name,dr.maximum_clinical_stage,
               a.association_class,a.evidence_strength_class,
               GROUP_CONCAT(DISTINCT e.evidence_subtype SEPARATOR ' | ') evidence_subtypes,
               GROUP_CONCAT(DISTINCT e.source SEPARATOR ' | ') evidence_sources,
               GROUP_CONCAT(DISTINCT e.source_id SEPARATOR ' | ') evidence_source_ids
        FROM disease_drug_association a
        JOIN disease d ON d.disease_id=a.disease_id
        JOIN drug dr ON dr.drug_id=a.drug_id
        LEFT JOIN disease_drug_evidence e
          ON e.disease_drug_association_id=a.disease_drug_association_id
        WHERE d.disease_id IN ($din) $phaseSql
        GROUP BY a.disease_drug_association_id,d.disease_id,d.disease_name,
                 dr.drug_id,dr.preferred_name,dr.maximum_clinical_stage,
                 a.association_class,a.evidence_strength_class
        LIMIT 240
    ");
    $s->execute($p);

    foreach ($s as $r) {
        add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
        add_node($nodes,'drug',$r['drug_id'],$r['preferred_name'],['origin'=>'direct therapeutic evidence']);
        add_edge($edges,'dda::'.$r['disease_drug_association_id'],
            'disease::'.$r['disease_id'],'drug::'.$r['drug_id'],'direct_disease_drug',[
                'label'=>$r['evidence_strength_class'] ?: 'direct evidence',
                'association_class'=>$r['association_class'],
                'evidence_subtypes'=>$r['evidence_subtypes'],
                'evidence_sources'=>$r['evidence_sources'],
                'evidence_source_ids'=>$r['evidence_source_ids'],
                'clinical_stage'=>$r['maximum_clinical_stage']
            ]);
    }
}

/* Target-overlap discovery remains separate from direct therapeutic evidence. */
if ($overlap && $graphDiseaseIds) {
    $ids = array_keys($graphDiseaseIds);
    $p = [];
    $din = in_clause($ids,'ovd',$p);
    $phaseSql = '';
    if ($phase !== '') {
        $phaseSql = " AND dr.maximum_clinical_stage=:phase";
        $p[':phase'] = $phase;
    }

    $s = $pdo->prepare("
        SELECT s.summary_id,d.disease_id,d.disease_name,
               dr.drug_id,dr.preferred_name,s.target_gene_count,s.target_genes
        FROM disease_drug_target_overlap_summary s
        JOIN disease d ON d.disease_id=s.disease_id
        JOIN drug dr ON dr.drug_id=s.drug_id
        WHERE s.direct_disease_drug_evidence=0
          AND d.disease_id IN ($din) $phaseSql
        LIMIT 180
    ");
    $s->execute($p);

    foreach ($s as $r) {
        add_node($nodes,'disease',$r['disease_id'],$r['disease_name']);
        add_node($nodes,'drug',$r['drug_id'],$r['preferred_name'],['origin'=>'target-overlap discovery']);
        add_edge($edges,'overlap::'.$r['summary_id'],
            'disease::'.$r['disease_id'],'drug::'.$r['drug_id'],'target_overlap_only',[
                'label'=>'target overlap',
                'target_gene_count'=>(int)$r['target_gene_count'],
                'target_genes'=>$r['target_genes'],
                'warning'=>'Discovery connection only; not direct therapeutic evidence.'
            ]);
    }
}

/*
 * Molecular drug-target expansion:
 * When genes are explicitly selected, expand from those genes.
 * Otherwise, limit target edges to genes already present in the graph.
 */
if ($target && $graphGeneIds) {
    $ids = $selectedGenes ?: array_keys($graphGeneIds);
    $p = [];
    $gin = in_clause($ids,'tg',$p);

    $s = $pdo->prepare("
        SELECT a.drug_target_association_id,dr.drug_id,dr.preferred_name,
               g.hgnc_id,g.gene_symbol,a.mechanism_of_action,a.action_type,
               a.source,a.source_id
        FROM drug_target_association a
        JOIN drug dr ON dr.drug_id=a.drug_id
        JOIN gene g ON g.hgnc_id=a.hgnc_id
        WHERE g.hgnc_id IN ($gin)
        LIMIT 220
    ");
    $s->execute($p);

    foreach ($s as $r) {
        add_node($nodes,'gene',$r['hgnc_id'],$r['gene_symbol'],[
            'selected_for_expansion'=>in_array($r['hgnc_id'],$selectedGenes,true) ? 1 : 0
        ]);
        add_node($nodes,'drug',$r['drug_id'],$r['preferred_name'],['origin'=>'drug target']);
        add_edge($edges,'dta::'.$r['drug_target_association_id'],
            'drug::'.$r['drug_id'],'gene::'.$r['hgnc_id'],'drug_target',[
                'label'=>$r['action_type'] ?: 'target',
                'mechanism_of_action'=>$r['mechanism_of_action'],
                'source_name'=>$r['source'],
                'source_id'=>$r['source_id']
            ]);
    }
}

json_response([
    'ok'=>true,
    'elements'=>array_merge(array_values($nodes),array_values($edges)),
    'counts'=>[
        'nodes'=>count($nodes),
        'edges'=>count($edges),
        'diseases'=>count(array_filter(array_keys($nodes),static fn($k)=>str_starts_with($k,'disease::'))),
        'genes'=>count(array_filter(array_keys($nodes),static fn($k)=>str_starts_with($k,'gene::')))
    ],
    'state'=>[
        'seed_diseases'=>$seedDiseases,
        'selected_genes'=>$selectedGenes,
        'expand_gene_diseases'=>$expandGeneDiseases,
        'include_neighbor_genes'=>$includeNeighborGenes
    ]
]);
