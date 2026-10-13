<?php
declare(strict_types=1);
/**
 * ODDB v1 scientific statistics snapshot builder.
 * CLI ONLY. Reads canonical ODDB tables using the same read-only web credentials.
 * Example in web container:
 *   php /srv/oddb/app/public/api/build_statistics_cli.php
 * Generated static JSON must be copied out and committed alongside the source.
 */
if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}
require_once __DIR__ . '/db.php';
$pdo = oddb_db();
$target = __DIR__ . '/../assets/statistics_data';
if (!is_dir($target) && !mkdir($target, 0755, true) && !is_dir($target)) {
    throw new RuntimeException('Cannot create statistics output directory');
}
function stats_rows(PDO $pdo, string $sql): array {
    $stm = $pdo->query($sql);
    return $stm->fetchAll(PDO::FETCH_ASSOC);
}
function stats_write(string $dir, string $filename, array $payload): array {
    $json = json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR) . "\n";
    $temp = tempnam($dir, '.stats-');
    if ($temp === false || file_put_contents($temp, $json, LOCK_EX) === false) {
        throw new RuntimeException("Unable to write $filename");
    }
    chmod($temp, 0644);
    if (!rename($temp, "$dir/$filename")) {
        throw new RuntimeException("Unable to finalize $filename");
    }
    return ['file'=>$filename, 'bytes'=>strlen($json), 'sha256'=>hash('sha256', $json)];
}
function stats_matrix(PDO $pdo, string $sql, string $nameKey, string $countKey = 'n'): array {
    $result = [];
    foreach (stats_rows($pdo, $sql) as $r) {
        $id = (string)$r['entity_id'];
        if (!isset($result[$id])) {
            $result[$id] = ['id'=>$id, 'name'=>(string)$r[$nameKey], 'total'=>0, 'parts'=>[]];
        }
        $part = (string)$r['part'];
        $n = (int)$r[$countKey];
        $result[$id]['total'] += $n;
        $result[$id]['parts'][$part] = $n;
    }
    foreach ($result as &$entry) ksort($entry['parts'], SORT_NATURAL | SORT_FLAG_CASE);
    unset($entry);
    $result = array_values($result);
    usort($result, static fn(array $a, array $b): int =>
        ($b['total'] <=> $a['total']) ?: strcasecmp($a['name'], $b['name']));
    return $result;
}

/**
 * Map a chromosome or HGNC cytogenetic location to a canonical chromosome.
 * Multiple locations from different chromosomes remain Unmapped, never guessed.
 */
function stats_chromosome(?string $raw): string {
    $value = trim((string)$raw);
    if ($value === '') return 'Unmapped';
    if (preg_match('/^(?:chr)?(MT|M)$/i', $value) || stripos($value, 'mitochondri') === 0) return 'MT';
    $found = [];
    if (preg_match_all('/(?:^|[\\s,;|\\/])(?:chr)?(2[0-2]|1[0-9]|[1-9]|X|Y)(?=[pq](?:\\d|$)|$)/i', $value, $matches)) {
        foreach ($matches[1] as $x) $found[strtoupper($x)] = true;
    }
    return count($found) === 1 ? (string)array_key_first($found) : 'Unmapped';
}

/**
 * Only approved HGNC entries are used, joined on the stable HGNC identifier.
 * This is an external, read-only annotation overlay. No SQL tables are edited.
 */
function stats_hgnc_annotation(PDO $pdo): array {
    $file = (string)(getenv('ODDB_HGNC_TSV') ?: '');
    $genes = stats_rows($pdo, 'SELECT hgnc_id,chromosome FROM gene');
    $fromCanonical = [];
    foreach ($genes as $r) {
        $chr = stats_chromosome($r['chromosome']);
        if ($chr !== 'Unmapped') $fromCanonical[(string)$r['hgnc_id']] = $chr;
    }
    $reference = [];
    if ($file !== '') {
        if (!is_file($file) || !is_readable($file)) throw new RuntimeException('HGNC annotation file is not readable');
        $fp = fopen($file,'rb');
        if ($fp === false) throw new RuntimeException('Cannot open HGNC TSV');
        $head = fgetcsv($fp, 0, "\t");
        if (!$head) throw new RuntimeException('Empty HGNC TSV');
        $head = array_map(static fn($v) => ltrim(trim((string)$v), "\xEF\xBB\xBF"), $head);
        $fields = array_flip($head);
        foreach (['hgnc_id','location','status'] as $key) {
            if (!isset($fields[$key])) throw new RuntimeException("HGNC TSV column missing: $key");
        }
        while (($row = fgetcsv($fp, 0, "\t")) !== false) {
            if (count($row) <= max($fields['hgnc_id'], $fields['location'], $fields['status'])) continue;
            if (strcasecmp(trim((string)$row[$fields['status']]), 'Approved') !== 0) continue;
            $id = trim((string)$row[$fields['hgnc_id']]);
            $chr = stats_chromosome($row[$fields['location']]);
            if ($id !== '' && $chr !== 'Unmapped') $reference[$id] = $chr;
        }
        fclose($fp);
    }
    $lookup = $fromCanonical;
    $overlayMatched = 0;
    foreach ($genes as $r) {
        $id = (string)$r['hgnc_id'];
        if (!isset($lookup[$id]) && isset($reference[$id])) {
            $lookup[$id] = $reference[$id];
            $overlayMatched++;
        }
    }
    if (count($lookup) === 0) {
        throw new RuntimeException('No gene chromosome assignments. Supply a dated HGNC TSV via ODDB_HGNC_TSV.');
    }
    return [
        $lookup,
        [
            'source' => $file !== '' ? 'HGNC complete approved set (external annotation overlay)' : 'ODDB canonical gene chromosome fields',
            'file_basename' => $file !== '' ? basename($file) : null,
            'source_sha256' => $file !== '' ? hash_file('sha256',$file) : null,
            'canonical_annotated' => count($fromCanonical),
            'overlay_matched' => $overlayMatched,
            'annotated' => count($lookup),
            'unmapped' => count($genes) - count($lookup),
            'total_genes' => count($genes),
            'method' => 'Approved HGNC ID exact match; chromosome inferred from cytogenetic location; ambiguous locations unmapped'
        ]
    ];
}

function stats_add_distinct(array &$matrix, string $id, string $name, string $part, string $member): void {
    if (!isset($matrix[$id])) $matrix[$id] = ['id'=>$id,'name'=>$name,'parts'=>[]];
    $matrix[$id]['parts'][$part][$member] = true;
}
function stats_finish_distinct(array $matrix): array {
    $result = [];
    foreach ($matrix as $r) {
        $parts = [];
        foreach ($r['parts'] as $part=>$members) $parts[$part] = count($members);
        ksort($parts, SORT_NATURAL | SORT_FLAG_CASE);
        $result[] = ['id'=>$r['id'],'name'=>$r['name'],'total'=>array_sum($parts),'parts'=>$parts];
    }
    usort($result,static fn($a,$b)=>($b['total']<=>$a['total']) ?: strcasecmp($a['name'],$b['name']));
    return $result;
}

[$geneChromosomes, $geneLocationMetadata] = stats_hgnc_annotation($pdo);
$genesDisease = [];
$genesChromCategory = [];
$genesCategoryChrom = [];
foreach (stats_rows($pdo, <<<'SQL'
    SELECT DISTINCT a.disease_id,d.disease_name,a.hgnc_id,
                    dc.category_id,dc.category_name
    FROM disease_gene_association a
    JOIN disease d ON d.disease_id=a.disease_id
    LEFT JOIN disease_category_membership m ON m.disease_id=a.disease_id
    LEFT JOIN disease_category dc ON dc.category_id=m.category_id
                                  AND dc.category_system='anatomy'
    SQL) as $r) {
    $gid = (string)$r['hgnc_id'];
    $chr = $geneChromosomes[$gid] ?? 'Unmapped';
    stats_add_distinct($genesDisease,(string)$r['disease_id'],(string)$r['disease_name'],$chr,$gid);
    if ($r['category_id'] !== null) {
        stats_add_distinct($genesChromCategory,$chr,$chr,(string)$r['category_name'],$gid);
        stats_add_distinct($genesCategoryChrom,(string)$r['category_id'],(string)$r['category_name'],$chr,$gid);
    }
}

/** Highest reported phase per unique disease–drug pair across shared trials. */
function stats_phase_priority(string $phase): float {
    $s = strtoupper(preg_replace('/[\\s-]+/', '_', trim($phase)));
    if (str_contains($s,'EARLY_PHASE')) return 0.5;
    if (preg_match_all('/PHASE_?([0-4])/', $s, $matches)) return (float)max(array_map('intval',$matches[1]));
    if ($s === 'NOT_APPLICABLE') return -1.0;
    if ($s === 'UNKNOWN') return -2.0;
    return -3.0;
}
$trialPairs = [];
foreach (stats_rows($pdo, <<<'SQL'
    SELECT DISTINCT dct.disease_id,d.disease_name,drct.drug_id,dr.preferred_name,ct.phase
    FROM disease_clinical_trial_association dct
    JOIN disease d ON d.disease_id=dct.disease_id
    JOIN clinical_trial ct ON ct.clinical_trial_id=dct.clinical_trial_id
    JOIN drug_clinical_trial_association drct ON drct.clinical_trial_id=ct.clinical_trial_id
    JOIN drug dr ON dr.drug_id=drct.drug_id
    SQL) as $r) {
    $did = (string)$r['disease_id']; $drugId = (string)$r['drug_id'];
    $key = $did."\x1f".$drugId;
    $phase = trim((string)$r['phase']) ?: 'NO_PHASE_REPORTED';
    $rank = stats_phase_priority($phase);
    if (!isset($trialPairs[$key]) || $rank > $trialPairs[$key]['rank'] ||
        ($rank === $trialPairs[$key]['rank'] && strcmp($phase,$trialPairs[$key]['phase']) < 0)) {
        $trialPairs[$key] = [
            'disease_id'=>$did,'disease_name'=>(string)$r['disease_name'],
            'drug_id'=>$drugId,'drug_name'=>(string)$r['preferred_name'],
            'phase'=>$phase,'rank'=>$rank
        ];
    }
}
$diseasesTrialDrugs = [];
$drugsTrialDiseases = [];
foreach ($trialPairs as $r) {
    stats_add_distinct($diseasesTrialDrugs,$r['disease_id'],$r['disease_name'],$r['phase'],$r['drug_id']);
    stats_add_distinct($drugsTrialDiseases,$r['drug_id'],$r['drug_name'],$r['phase'],$r['disease_id']);
}

// Only canonical disease/variant/gene keys are counted; membership overlaps
// across categories are intentional and MUST NOT be summed as unique totals.
$rankings = [
    'diseases_genes' => stats_finish_distinct($genesDisease),
    'diseases_variants' => stats_matrix($pdo, <<<'SQL'
        SELECT d.disease_id entity_id,d.disease_name name,
               COALESCE(NULLIF(TRIM(v.chromosome),''),'Unmapped') part,
               COUNT(DISTINCT a.variant_id) n
        FROM disease_variant_association a
        JOIN disease d ON d.disease_id=a.disease_id
        JOIN variant v ON v.variant_id=a.variant_id
        GROUP BY d.disease_id,d.disease_name,part
        SQL, 'name'),
    'genes_diseases' => stats_matrix($pdo, <<<'SQL'
        SELECT g.hgnc_id entity_id,g.gene_symbol name,'Diseases' part,
               COUNT(DISTINCT a.disease_id) n
        FROM disease_gene_association a
        JOIN gene g ON g.hgnc_id=a.hgnc_id
        GROUP BY g.hgnc_id,g.gene_symbol
        SQL, 'name'),
    // Trial-associated drugs are inferred ONLY via a shared clinical_trial_id.
    // This is trial co-occurrence, not a proven treatment or trial arm match.
    'diseases_trial_drugs' => stats_finish_distinct($diseasesTrialDrugs),
    'drugs_trial_diseases' => stats_finish_distinct($drugsTrialDiseases)
];

$chromosomes = [
    'genes_by_chromosome_category' => stats_finish_distinct($genesChromCategory),
    'variants_by_chromosome_category' => stats_matrix($pdo, <<<'SQL'
        SELECT COALESCE(NULLIF(TRIM(v.chromosome),''),'Unmapped') entity_id,
               COALESCE(NULLIF(TRIM(v.chromosome),''),'Unmapped') name,
               dc.category_name part,COUNT(DISTINCT a.variant_id) n
        FROM disease_variant_association a
        JOIN variant v ON v.variant_id=a.variant_id
        JOIN disease_category_membership m ON m.disease_id=a.disease_id
        JOIN disease_category dc ON dc.category_id=m.category_id AND dc.category_system='anatomy'
        GROUP BY entity_id,name,dc.category_id,dc.category_name
        SQL, 'name'),
    'genes_by_category_chromosome' => stats_finish_distinct($genesCategoryChrom),
    'variants_by_category_chromosome' => stats_matrix($pdo, <<<'SQL'
        SELECT dc.category_id entity_id,dc.category_name name,
               COALESCE(NULLIF(TRIM(v.chromosome),''),'Unmapped') part,
               COUNT(DISTINCT a.variant_id) n
        FROM disease_category dc
        JOIN disease_category_membership m ON m.category_id=dc.category_id
        JOIN disease_variant_association a ON a.disease_id=m.disease_id
        JOIN variant v ON v.variant_id=a.variant_id
        WHERE dc.category_system='anatomy'
        GROUP BY dc.category_id,dc.category_name,part
        SQL, 'name')
];

// IMPORTANT: disease_category memberships can overlap across the 12 systems.
$clinical = [
    'trial_phases' => array_map(static fn(array $r): array => [
        'phase'=>(string)$r['phase'], 'trials'=>(int)$r['trials']
    ], stats_rows($pdo, <<<'SQL'
        SELECT COALESCE(NULLIF(TRIM(phase),''),'NO_PHASE_REPORTED') phase,
               COUNT(DISTINCT clinical_trial_id) trials
        FROM clinical_trial
        GROUP BY COALESCE(NULLIF(TRIM(phase),''),'NO_PHASE_REPORTED')
        ORDER BY trials DESC,phase
        SQL)),
    'disease_categories' => array_map(static fn(array $r): array => [
        'id'=>(string)$r['category_id'], 'name'=>(string)$r['category_name'],
        'count'=>(int)$r['disease_count']
    ], stats_rows($pdo, <<<'SQL'
        SELECT dc.category_id,dc.category_name,COUNT(DISTINCT m.disease_id) disease_count
        FROM disease_category dc
        LEFT JOIN disease_category_membership m ON m.category_id=dc.category_id
        WHERE dc.category_system='anatomy'
        GROUP BY dc.category_id,dc.category_name,dc.display_order
        ORDER BY dc.display_order
        SQL)),
    'evidence_classes' => [
        ['name'=>'Direct only','count'=>(int)$pdo->query(<<<'SQL'
            SELECT COUNT(*) FROM disease_drug_association a
            WHERE NOT EXISTS(SELECT 1 FROM disease_drug_target_overlap_summary b
                             WHERE a.disease_id=b.disease_id AND a.drug_id=b.drug_id)
            SQL)->fetchColumn()],
        ['name'=>'Direct + target overlap','count'=>(int)$pdo->query(<<<'SQL'
            SELECT COUNT(*) FROM disease_drug_target_overlap_summary WHERE direct_disease_drug_evidence=1
            SQL)->fetchColumn()],
        ['name'=>'Target overlap only','count'=>(int)$pdo->query(<<<'SQL'
            SELECT COUNT(*) FROM disease_drug_target_overlap_summary WHERE direct_disease_drug_evidence=0
            SQL)->fetchColumn()]
    ],
    'diseases_for_network' => array_map(static fn(array $r): array => [
        'id'=>(string)$r['disease_id'], 'name'=>(string)$r['disease_name']
    ], stats_rows($pdo, <<<'SQL'
        SELECT disease_id,disease_name FROM disease ORDER BY disease_name,disease_id
        SQL))
];

$files = [];
foreach ([
    'rankings.json'=>$rankings,
    'chromosomes.json'=>$chromosomes,
    'clinical.json'=>$clinical
] as $file=>$dataset) {
    $files[] = stats_write($target, $file, $dataset);
}
$sourceCounts = [];
foreach (['disease','gene','variant','drug','disease_gene_association','drug_target_association',
          'disease_drug_association','clinical_trial','clinical_report'] as $table) {
    // Fixed allowlist: table identifiers never come from user input.
    $sourceCounts[$table] = (int)$pdo->query('SELECT COUNT(*) FROM `'.$table.'`')->fetchColumn();
}
$releaseRecords = stats_rows($pdo,
    'SELECT release_key,manifest_sha256,status FROM oddb_release ORDER BY release_key');
$index = [
    'source_table_counts'=>$sourceCounts,
    'release_records'=>$releaseRecords,
    'gene_chromosome_annotation'=>$geneLocationMetadata,
    'trial_shared_disease_drug_pairs'=>count($trialPairs),
    'database_release'=>'ODDB v1 refined clinical/drug release 2026-09-30',
    'generated_utc'=>gmdate('c'),
    'generator'=>'api/build_statistics_cli.php',
    'methodology'=>[
        'rankings'=>'Distinct canonical entities. Each shared-trial disease-drug pair assigned to its highest reported trial phase; phase stacks sum to globally distinct pairs.',
        'anatomy'=>'Category memberships overlap; category or chromosome stacks are not globally additive. Gene chromosomes are exact HGNC ID matches from a dated annotation overlay.',
        'trial'=>'A disease and drug sharing a clinical trial is co-occurrence evidence, not proof of treatment.',
        'target_overlap'=>'Target-only connections are discovery hypotheses, not direct therapeutic evidence.'
    ],
    'files'=>$files
];
stats_write($target,'index.json',$index);
fwrite(STDOUT, "ODDB v1 statistics JSON generated in $target\n");
foreach ($files as $f) fwrite(STDOUT, "$f[file] $f[bytes] bytes sha256=$f[sha256]\n");
