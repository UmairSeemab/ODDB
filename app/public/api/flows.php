<?php
declare(strict_types=1);
require_once __DIR__.'/db.php';

$pdo = oddb_db();

$type = qparam('type', 'disease');
$limitRaw = qparam('limit', '40');

$allowed = ['disease','gene','variant','therapeutic'];
if (!in_array($type, $allowed, true)) {
    api_error('Unsupported flow type.', 400, ['allowed'=>$allowed]);
}

if ($limitRaw === 'all' || $limitRaw === '0') {
    $diseaseLimit = 0;
} else {
    $diseaseLimit = max(10, (int)$limitRaw);
}

function rows(PDO $pdo, string $sql, array $params=[]): array {
    $s = $pdo->prepare($sql);
    $s->execute($params);
    return $s->fetchAll();
}

function scalar(PDO $pdo, string $sql, array $params=[]): int {
    $s = $pdo->prepare($sql);
    $s->execute($params);
    return (int)$s->fetchColumn();
}

function short_label(string $s, int $max=34): string {
    $s = trim($s);
    if (mb_strlen($s) <= $max) return $s;
    return mb_substr($s, 0, $max-1).'…';
}

function node_id(string $prefix, string $id): string {
    return $prefix.'|'.$id;
}

/**
 * Build a three-layer Sankey:
 * left category -> disease -> right category.
 *
 * $paths rows require:
 *   left_id, left_name, disease_id, disease_name, right_id, right_name, path_value
 *
 * If a disease limit is used, only the selected diseases are drawn.
 * Omitted diseases remain excluded from the visible Sankey and are reported
 * through metadata rather than collapsed into an artificial node.
 */
function build_flow(
    array $paths,
    int $diseaseLimit,
    string $leftLayer,
    string $rightLayer,
    string $unit,
    int $totalCanonicalDiseases
): array {
    /*
     * Filtered Sankey behavior:
     * - rank diseases by total path weight for the selected flow
     * - show only the selected Top N diseases
     * - DO NOT create aggregate "other/additional diseases" nodes
     * - preserve full-flow totals in metadata so the UI can state clearly
     *   that the visible Sankey is a filtered view
     */

    $diseaseWeights = [];
    $diseaseNames = [];

    foreach ($paths as $r) {
        $did = (string)$r['disease_id'];
        $v = max(0, (int)$r['path_value']);
        $diseaseWeights[$did] = ($diseaseWeights[$did] ?? 0) + $v;
        $diseaseNames[$did] = (string)$r['disease_name'];
    }

    arsort($diseaseWeights, SORT_NUMERIC);
    $allDiseaseIds = array_keys($diseaseWeights);

    $shownDiseaseIds = $diseaseLimit > 0
        ? array_slice($allDiseaseIds, 0, $diseaseLimit)
        : $allDiseaseIds;

    $shown = array_fill_keys($shownDiseaseIds, true);

    $nodeMap = [];
    $linkMap = [];

    $addNode = function(
        string $id, string $label, string $fullLabel, string $layer,
        string $kind, ?string $refId=null, ?string $url=null
    ) use (&$nodeMap): void {
        if (!isset($nodeMap[$id])) {
            $nodeMap[$id] = [
                'name'=>$id,
                'label'=>$label,
                'full_label'=>$fullLabel,
                'layer'=>$layer,
                'kind'=>$kind,
                'ref_id'=>$refId,
                'url'=>$url
            ];
        }
    };

    $addLink = function(string $source, string $target, int $value) use (&$linkMap): void {
        if ($value <= 0) return;
        $k = $source."\x1f".$target;
        if (!isset($linkMap[$k])) {
            $linkMap[$k] = ['source'=>$source,'target'=>$target,'value'=>0];
        }
        $linkMap[$k]['value'] += $value;
    };

    $fullPathTotal = 0;
    $visiblePathTotal = 0;

    foreach ($paths as $r) {
        $value = max(0, (int)$r['path_value']);
        $fullPathTotal += $value;

        $didRaw = (string)$r['disease_id'];
        if (!isset($shown[$didRaw])) {
            continue;
        }

        $visiblePathTotal += $value;

        $leftId = node_id('L', (string)$r['left_id']);
        $leftName = (string)$r['left_name'];

        $diseaseId = node_id('D', $didRaw);
        $diseaseName = (string)$r['disease_name'];

        $rightId = node_id('R', (string)$r['right_id']);
        $rightName = (string)$r['right_name'];

        $leftUrl = null;
        if ($leftLayer === 'Anatomy category') {
            $leftUrl = 'explore.php?system=anatomy&category='.rawurlencode((string)$r['left_id']).'&mode=gene';
        } elseif ($leftLayer === 'Inheritance category') {
            $leftUrl = 'explore.php?system=inheritance&category='.rawurlencode((string)$r['left_id']).'&mode=gene';
        }

        $addNode(
            $leftId,
            short_label($leftName, 24),
            $leftName,
            $leftLayer,
            'left',
            (string)$r['left_id'],
            $leftUrl
        );

        $addNode(
            $diseaseId,
            short_label($diseaseName, 30),
            $diseaseName,
            'Disease',
            'disease',
            $didRaw,
            'explore.php?type=disease&id='.rawurlencode($didRaw)
        );

        $addNode(
            $rightId,
            short_label($rightName, 28),
            $rightName,
            $rightLayer,
            'right',
            (string)$r['right_id'],
            null
        );

        $addLink($leftId, $diseaseId, $value);
        $addLink($diseaseId, $rightId, $value);
    }

    return [
        'nodes'=>array_values($nodeMap),
        'links'=>array_values($linkMap),
        'meta'=>[
            'canonical_diseases'=>$totalCanonicalDiseases,
            'diseases_with_paths'=>count($allDiseaseIds),
            'disease_nodes_shown'=>count($shownDiseaseIds),
            'disease_nodes_omitted'=>max(0, count($allDiseaseIds)-count($shownDiseaseIds)),
            'disease_limit'=>$diseaseLimit === 0 ? 'all' : $diseaseLimit,
            'visible_path_units'=>$visiblePathTotal,
            'total_path_units'=>$fullPathTotal,
            'path_units'=>$visiblePathTotal,
            'sankey_links'=>count($linkMap),
            'unit'=>$unit
        ]
    ];
}

$totalDiseases = scalar($pdo, "SELECT COUNT(*) FROM disease");

if ($type === 'disease') {
    /*
     * One path unit = one anatomy -> disease -> inheritance classification path.
     * For diseases with no direct supported inheritance membership, the endpoint
     * uses a visual "Not classified" state. This is not a biological inheritance
     * category and is explicitly labelled as absence of direct classification.
     */
    $paths = rows($pdo, "
        SELECT
            ac.category_id AS left_id,
            ac.category_name AS left_name,
            d.disease_id,
            d.disease_name,
            COALESCE(ic.category_id, 'NOT_CLASSIFIED') AS right_id,
            COALESCE(ic.category_name, 'Not classified') AS right_name,
            1 AS path_value
        FROM disease d
        JOIN disease_category_membership am
          ON am.disease_id=d.disease_id
        JOIN disease_category ac
          ON ac.category_id=am.category_id
         AND ac.category_system='anatomy'
        LEFT JOIN disease_category_membership im
          ON im.disease_id=d.disease_id
         AND EXISTS (
             SELECT 1
             FROM disease_category icx
             WHERE icx.category_id=im.category_id
               AND icx.category_system='inheritance'
         )
        LEFT JOIN disease_category ic
          ON ic.category_id=im.category_id
         AND ic.category_system='inheritance'
        ORDER BY ac.display_order, d.disease_name, ic.display_order
    ");

    $built = build_flow(
        $paths, $diseaseLimit,
        'Anatomy category', 'Inheritance category',
        'classification paths', $totalDiseases
    );

    json_response([
        'ok'=>true,
        'type'=>'disease',
        'title'=>'Disease classification flow',
        'subtitle'=>'Anatomy category → canonical disease → supported inheritance classification.',
        'note'=>'“Not classified” means ODDB has no direct supported disease-level inheritance classification; it is not an inheritance mode.',
        'ranking'=>'Most connected = highest number of classification paths (supported inheritance memberships; an unclassified disease contributes one path).',
        ...$built
    ]);
}

if ($type === 'gene') {
    /*
     * One path unit = one disease-gene association assigned to a gene category.
     * Disease-locus associations are added as the Genetic locus category.
     */
    $paths = rows($pdo, "
        SELECT
            ac.category_id AS left_id,
            ac.category_name AS left_name,
            d.disease_id,
            d.disease_name,
            gc.gene_category_id AS right_id,
            gc.category_name AS right_name,
            COUNT(DISTINCT dga.hgnc_id) AS path_value
        FROM disease d
        JOIN disease_category_membership am
          ON am.disease_id=d.disease_id
        JOIN disease_category ac
          ON ac.category_id=am.category_id
         AND ac.category_system='anatomy'
        JOIN disease_gene_association dga
          ON dga.disease_id=d.disease_id
        JOIN gene_category_membership gcm
          ON gcm.hgnc_id=dga.hgnc_id
        JOIN gene_category gc
          ON gc.gene_category_id=gcm.gene_category_id
         AND gc.entity_scope='gene'
        GROUP BY
            ac.category_id, ac.category_name,
            d.disease_id, d.disease_name,
            gc.gene_category_id, gc.category_name

        UNION ALL

        SELECT
            ac.category_id AS left_id,
            ac.category_name AS left_name,
            d.disease_id,
            d.disease_name,
            'GENE-02' AS right_id,
            'Genetic locus' AS right_name,
            COUNT(DISTINCT dla.locus_id) AS path_value
        FROM disease d
        JOIN disease_category_membership am
          ON am.disease_id=d.disease_id
        JOIN disease_category ac
          ON ac.category_id=am.category_id
         AND ac.category_system='anatomy'
        JOIN disease_locus_association dla
          ON dla.disease_id=d.disease_id
        GROUP BY
            ac.category_id, ac.category_name,
            d.disease_id, d.disease_name

        ORDER BY left_name, disease_name, right_name
    ");

    $built = build_flow(
        $paths, $diseaseLimit,
        'Anatomy category', 'Gene / locus category',
        'disease–gene/locus associations', $totalDiseases
    );

    json_response([
        'ok'=>true,
        'type'=>'gene',
        'title'=>'Gene architecture flow',
        'subtitle'=>'Anatomy category → canonical disease → gene or locus category.',
        'note'=>'Flow width represents distinct disease–gene or disease–locus associations, not gene expression or causal-strength scores.',
        'ranking'=>'Most connected = highest number of disease–gene/locus association paths in this flow.',
        ...$built
    ]);
}

if ($type === 'variant') {
    /*
     * One path unit = one disease-variant link for a variant carrying a mapped
     * ODDB consequence annotation. Only canonical DVA rows are used.
     */
    $paths = rows($pdo, "
        SELECT
            ac.category_id AS left_id,
            ac.category_name AS left_name,
            d.disease_id,
            d.disease_name,
            vcc.consequence_id AS right_id,
            vcc.consequence_term AS right_name,
            COUNT(DISTINCT dva.variant_id) AS path_value
        FROM disease d
        JOIN disease_category_membership am
          ON am.disease_id=d.disease_id
        JOIN disease_category ac
          ON ac.category_id=am.category_id
         AND ac.category_system='anatomy'
        JOIN disease_variant_association dva
          ON dva.disease_id=d.disease_id
        JOIN variant_consequence vc
          ON vc.variant_id=dva.variant_id
        JOIN variant_consequence_category vcc
          ON vcc.consequence_id=vc.consequence_id
        GROUP BY
            ac.category_id, ac.category_name,
            d.disease_id, d.disease_name,
            vcc.consequence_id, vcc.consequence_term
        ORDER BY ac.category_name, d.disease_name, vcc.display_order
    ");

    $built = build_flow(
        $paths, $diseaseLimit,
        'Anatomy category', 'Variant consequence',
        'annotated disease–variant links', $totalDiseases
    );

    $allConsequenceCategories = scalar($pdo, "SELECT COUNT(*) FROM variant_consequence_category");
    $representedConsequenceCategories = scalar($pdo, "
        SELECT COUNT(DISTINCT vc.consequence_id)
        FROM disease_variant_association dva
        JOIN variant_consequence vc ON vc.variant_id=dva.variant_id
    ");
    $built['meta']['all_consequence_categories'] = $allConsequenceCategories;
    $built['meta']['represented_consequence_categories'] = $representedConsequenceCategories;

    json_response([
        'ok'=>true,
        'type'=>'variant',
        'title'=>'Variant consequence flow',
        'subtitle'=>'Anatomy category → canonical disease → mapped variant consequence.',
        'note'=>'Only canonical disease–variant associations whose variants have mapped consequence annotations contribute to flow width. The full ODDB taxonomy retains all 21 consequence categories.',
        'ranking'=>'Most connected = highest number of annotated disease–variant paths in this flow.',
        ...$built
    ]);
}

if ($type === 'therapeutic') {
    /*
     * One path unit = one UNIQUE disease–drug pair.
     *
     * Pair classes:
     *   Direct therapeutic evidence only
     *   Direct evidence + target overlap
     *   Target-overlap discovery only
     *
     * Diseases with neither direct disease–drug evidence nor target-overlap
     * discovery are counted separately in metadata. They are deliberately NOT
     * inserted into the Sankey because that would mix "number of diseases"
     * with "number of disease–drug pairs" in the same flow widths.
     */
    $paths = rows($pdo, "
        SELECT
            ac.category_id AS left_id,
            ac.category_name AS left_name,
            d.disease_id,
            d.disease_name,
            x.class_id AS right_id,
            x.class_name AS right_name,
            COUNT(DISTINCT x.drug_id) AS path_value
        FROM disease d
        JOIN disease_category_membership am
          ON am.disease_id=d.disease_id
        JOIN disease_category ac
          ON ac.category_id=am.category_id
         AND ac.category_system='anatomy'
        JOIN (
            SELECT
                dda.disease_id,
                dda.drug_id,
                'DIRECT_ONLY' AS class_id,
                'Direct therapeutic evidence only' AS class_name
            FROM disease_drug_association dda
            WHERE NOT EXISTS (
                SELECT 1
                FROM disease_drug_target_overlap_summary s
                WHERE s.disease_id=dda.disease_id
                  AND s.drug_id=dda.drug_id
            )

            UNION ALL

            SELECT
                s.disease_id,
                s.drug_id,
                'DIRECT_PLUS_TARGET' AS class_id,
                'Direct evidence + target overlap' AS class_name
            FROM disease_drug_target_overlap_summary s
            WHERE s.direct_disease_drug_evidence=1

            UNION ALL

            SELECT
                s.disease_id,
                s.drug_id,
                'TARGET_ONLY' AS class_id,
                'Target-overlap discovery only' AS class_name
            FROM disease_drug_target_overlap_summary s
            WHERE s.direct_disease_drug_evidence=0
        ) x
          ON x.disease_id=d.disease_id
        GROUP BY
            ac.category_id, ac.category_name,
            d.disease_id, d.disease_name,
            x.class_id, x.class_name
        ORDER BY left_name, disease_name, right_name
    ");

    $diseasesWithoutLinkedDrugEvidence = scalar($pdo, "
        SELECT COUNT(*)
        FROM disease d
        WHERE NOT EXISTS (
            SELECT 1
            FROM disease_drug_association dda
            WHERE dda.disease_id=d.disease_id
        )
        AND NOT EXISTS (
            SELECT 1
            FROM disease_drug_target_overlap_summary s
            WHERE s.disease_id=d.disease_id
        )
    ");

    $built = build_flow(
        $paths, $diseaseLimit,
        'Anatomy category', 'Drug evidence class',
        'unique disease–drug pairs', $totalDiseases
    );

    $built['meta']['diseases_without_linked_drug_evidence'] =
        $diseasesWithoutLinkedDrugEvidence;

    json_response([
        'ok'=>true,
        'type'=>'therapeutic',
        'title'=>'Therapeutic evidence flow',
        'subtitle'=>'Anatomy category → canonical disease → disease–drug evidence class.',
        'note'=>'Flow width counts unique disease–drug pairs. Target-overlap-only pairs are discovery relationships and are not treatment assertions. Diseases without linked drug evidence are reported separately below and are not mixed into pair-count flow widths.',
        'ranking'=>'Most connected = highest number of unique disease–drug evidence/discovery pairs in this flow.',
        ...$built
    ]);
}
