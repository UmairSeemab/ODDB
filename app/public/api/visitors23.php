<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
function fail23(int $status): never {http_response_code($status);echo '{"ok":false,"error":"Visitor statistics temporarily unavailable"}';exit;}
function trusted23(string $ip): bool {
 $list=json_decode(getenv('ODDB_VISITOR_TRUSTED_PROXIES')?:'[]',true);
 return is_array($list)&&in_array($ip,$list,true);
}
$remote=$_SERVER['REMOTE_ADDR']??'';
$ip=$remote;
// Walk the proxy chain from right to left. Never accept a caller-selected leftmost address.
if(trusted23($remote)) {
 $chain=explode(',',$_SERVER['HTTP_X_FORWARDED_FOR']??'');
 for($i=count($chain)-1;$i>=0;$i--) {
  $candidate=trim($chain[$i]);
  if(!filter_var($candidate,FILTER_VALIDATE_IP)) { $ip=$remote;break; }
  $ip=$candidate;
  if(!trusted23($candidate))break;
 }
}
$method=$_SERVER['REQUEST_METHOD']??'GET';
if(!in_array($method,['GET','POST'],true))fail23(405);
if($method==='POST') {
 // Same-origin JSON requests only. Cross-origin forms cannot supply this content type.
 if(stripos($_SERVER['CONTENT_TYPE']??'','application/json')!==0)fail23(415);
 if(($_SERVER['HTTP_SEC_FETCH_SITE']??'same-origin')==='cross-site')fail23(403);
 if((int)($_SERVER['CONTENT_LENGTH']??0)>512)fail23(413);
 $body=json_decode(file_get_contents('php://input',false,null,0,513),true);
 if(!is_array($body))fail23(400);
} else {$body=[];}
$enabled=(getenv('ODDB_VISITOR_MODE')==='production')&&($_SERVER['HTTP_DNT']??'0')!=='1'&&($_SERVER['HTTP_SEC_GPC']??'0')!=='1';
$payload=json_encode(['ip'=>$ip,'ua'=>substr($_SERVER['HTTP_USER_AGENT']??'',0,256),'page'=>$body['page']??'','mode'=>$enabled?'production':'preview']);
$url=getenv('ODDB_VISITOR_URL')?:'';$token=getenv('ODDB_VISITOR_TOKEN')?:'';
if(!preg_match('~^http://oddb-visitors-23:8080$~',$url)||!preg_match('/^[a-f0-9]{64}$/',$token))fail23(503);
$context=stream_context_create(['http'=>['method'=>'POST','header'=>"Content-Type: application/json\r\nAuthorization: Bearer $token\r\nConnection: close\r\n",'content'=>$payload,'timeout'=>1.5,'ignore_errors'=>true]]);
$response=@file_get_contents($url.($method==='POST'?'/event':'/stats'),false,$context);
if($response===false)fail23(503);
$data=json_decode($response,true);
if(!is_array($data)||empty($data['ok']))fail23(503);
echo json_encode($data,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);
