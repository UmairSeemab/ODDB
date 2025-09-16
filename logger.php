<?php
$file = __DIR__ . "/visitors.json";

// Get real visitor IP dynamically
function getUserIP() {
    if (!empty($_SERVER['HTTP_CLIENT_IP'])) {
        return $_SERVER['HTTP_CLIENT_IP'];
    } elseif (!empty($_SERVER['HTTP_X_FORWARDED_FOR'])) {
        return explode(',', $_SERVER['HTTP_X_FORWARDED_FOR'])[0];
    } else {
        return $_SERVER['REMOTE_ADDR'] ?? "0.0.0.0";
    }
}

$ip = getUserIP();

// For localhost testing, try to get your public IP automatically
if ($ip === "127.0.0.1" || $ip === "::1") {
    // Fetch public IP from an external service
    $externalIP = @file_get_contents('https://api.ipify.org');
    if ($externalIP) {
        $ip = $externalIP;
    } else {
        $ip = "Unknown";
    }
}

$browser = $_SERVER['HTTP_USER_AGENT'] ?? "Unknown";
$time = date("Y-m-d H:i:s");

// Default location
$location = "Unknown";

// Fetch geolocation dynamically (skip if IP unknown)
if ($ip !== "Unknown") {
    $geo = @file_get_contents("http://ip-api.com/json/{$ip}");
    if ($geo) {
        $geoData = json_decode($geo, true);
        if (!empty($geoData['status']) && $geoData['status'] === "success") {
            $location = $geoData['city'] . ", " . $geoData['country'];
        }
    }
}

// Load existing visitors
$data = [];
if (file_exists($file)) {
    $json = file_get_contents($file);
    $data = json_decode($json, true);
    if (!is_array($data)) $data = [];
}

// Add new visitor at the end
$newVisitor = [
    "ip" => $ip,
    "browser" => $browser,
    "time" => $time,
    "location" => $location
];
$data[] = $newVisitor;

// Save back (keep full history)
file_put_contents($file, json_encode($data, JSON_PRETTY_PRINT));
