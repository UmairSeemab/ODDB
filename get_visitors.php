<?php
$file = __DIR__ . "/visitors.json";
$visitors = [];

// Read file
if (file_exists($file)) {
    $data = json_decode(file_get_contents($file), true);
    if (is_array($data)) {
        // Last 10 visitors (newest first)
        $visitors = array_slice(array_reverse($data), 0, 15);
    }
}

// Output JSON
header("Content-Type: application/json");
echo json_encode($visitors);
