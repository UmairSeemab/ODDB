<?php
declare(strict_types=1);

$catalogFile = dirname(__DIR__, 2).'/config/release_catalog.json';

if (!is_file($catalogFile)) {
    http_response_code(503);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode([
        'ok'=>false,
        'error'=>'Release catalog is missing. Run scripts/rebuild_release_catalog.py.'
    ]);
    exit;
}

$json = file_get_contents($catalogFile);
$data = json_decode($json, true);

if (!is_array($data)) {
    http_response_code(500);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['ok'=>false,'error'=>'Release catalog is invalid.']);
    exit;
}

$data['ok'] = true;

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: public, max-age=300');
echo json_encode(
    $data,
    JSON_UNESCAPED_UNICODE |
    JSON_UNESCAPED_SLASHES |
    JSON_PARTIAL_OUTPUT_ON_ERROR
);
