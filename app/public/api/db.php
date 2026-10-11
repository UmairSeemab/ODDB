<?php
declare(strict_types=1);
function oddb_db(): PDO {
    static $pdo=null;
    if($pdo instanceof PDO) return $pdo;
    $host=getenv('ODDB_DB_HOST')?:'127.0.0.1';
    $port=getenv('ODDB_DB_PORT')?:'3306';
    $name=getenv('ODDB_DB_NAME')?:'oddb_v1';
    $user=getenv('ODDB_DB_USER')?:'root';
    $pass=getenv('ODDB_DB_PASSWORD')?:'';
    $pdo=new PDO("mysql:host={$host};port={$port};dbname={$name};charset=utf8mb4",$user,$pass,[
      PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,
      PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC,
      PDO::ATTR_EMULATE_PREPARES=>false
    ]);
    return $pdo;
}
function json_response(array $data,int $status=200): never {
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($data,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_PARTIAL_OUTPUT_ON_ERROR);
    exit;
}
function api_error(string $message,int $status=400,array $extra=[]): never {
    json_response(array_merge(['ok'=>false,'error'=>$message],$extra),$status);
}
function qparam(string $k,string $default=''): string {
    $v=$_GET[$k]??$default; return is_string($v)?trim($v):$default;
}
function int_param(string $k,int $default,int $min,int $max): int {
    $v=filter_input(INPUT_GET,$k,FILTER_VALIDATE_INT);
    if($v===false||$v===null)return $default;
    return max($min,min($max,(int)$v));
}
function sql_like(string $s): string { return '%'.$s.'%'; }
set_exception_handler(function(Throwable $e): void { error_log((string)$e); api_error('Server error while processing the ODDB request.',500); });
