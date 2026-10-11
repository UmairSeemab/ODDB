<?php
declare(strict_types=1);

$id = isset($_GET['id']) && is_string($_GET['id']) ? trim($_GET['id']) : '';
if ($id === '' || !preg_match('/^[A-Za-z0-9._-]+$/', $id)) {
    http_response_code(400);
    exit('Invalid download identifier.');
}

$appRoot = dirname(__DIR__);
$projectRoot = dirname($appRoot);
$catalogFile = $appRoot.'/config/release_catalog.json';

if (!is_file($catalogFile)) {
    http_response_code(503);
    exit('Release catalog unavailable.');
}

$catalog = json_decode((string)file_get_contents($catalogFile), true);
$files = is_array($catalog) ? ($catalog['files'] ?? []) : [];

$entry = null;
foreach ($files as $file) {
    if (($file['id'] ?? '') === $id) {
        $entry = $file;
        break;
    }
}

if (!is_array($entry)) {
    http_response_code(404);
    exit('Release file not found.');
}

$relative = (string)($entry['relative_path'] ?? '');
$releaseRoot = realpath($projectRoot.'/retnet_pipeline/releases');
$path = realpath($projectRoot.'/'.$relative);

if ($releaseRoot === false || $path === false || !is_file($path)) {
    http_response_code(404);
    exit('Release file unavailable.');
}

/* Strictly require resolved path to remain inside the project releases directory. */
$prefix = rtrim($releaseRoot, DIRECTORY_SEPARATOR).DIRECTORY_SEPARATOR;
if (strncmp($path, $prefix, strlen($prefix)) !== 0) {
    http_response_code(403);
    exit('Download path rejected.');
}

$filename = basename($path);
$size = filesize($path);

header('Content-Type: application/octet-stream');
header('Content-Disposition: attachment; filename="'.addcslashes($filename, '"\\').'"');
if ($size !== false) {
    header('Content-Length: '.$size);
}
header('X-Content-Type-Options: nosniff');
header('Cache-Control: private, max-age=0, must-revalidate');

$fh = fopen($path, 'rb');
if ($fh === false) {
    http_response_code(500);
    exit('Could not open release file.');
}

while (!feof($fh)) {
    echo fread($fh, 1024 * 1024);
    flush();
}
fclose($fh);
