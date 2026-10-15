<?php
declare(strict_types=1);
$id=$_GET['id']??'';
if(!is_string($id)||!preg_match('/^[A-Za-z0-9._-]+$/',$id)){http_response_code(400);exit('Invalid download identifier.');}
$appRoot=dirname(__DIR__);$projectRoot=dirname($appRoot);
$catalog=json_decode((string)@file_get_contents($appRoot.'/config/release_catalog.json'),true);
if(!is_array($catalog)){http_response_code(503);exit('Release catalog unavailable.');}
$entry=null;foreach($catalog['files']??[] as $item)if(($item['id']??null)===$id){$entry=$item;break;}
if(!$entry){http_response_code(404);exit('Release file not found.');}
$relative=$entry['relative_path']??'';
if(!is_string($relative)||str_contains($relative,"\0")){http_response_code(403);exit('Download path rejected.');}
$enriched=($entry['group']??'')==='current';
$root=realpath($projectRoot.($enriched?'/enrichment_downloads':'/retnet_pipeline/releases'));
$path=realpath($projectRoot.'/'.$relative);
if(!$root||!$path||!is_file($path)){http_response_code(404);exit('Release file unavailable.');}
if(!str_starts_with($path,rtrim($root,DIRECTORY_SEPARATOR).DIRECTORY_SEPARATOR)){http_response_code(403);exit('Download path rejected.');}
$name=basename($path);
if(!preg_match('/^[A-Za-z0-9._-]+$/',$name)||$name!==($entry['filename']??'')){http_response_code(403);exit('Filename rejected.');}
$size=filesize($path);if($size!==($entry['size_bytes']??null)){http_response_code(409);exit('Release file size differs from its manifest.');}
header('Content-Type: '.(str_ends_with($name,'.gz')?'application/gzip':'application/octet-stream'));
header('Content-Disposition: attachment; filename="'.$name.'"');header('Content-Length: '.$size);
header('X-Content-Type-Options: nosniff');header('Cache-Control: public, max-age=3600');
if(isset($entry['sha256']))header('X-ODDB-SHA256: '.$entry['sha256']);
$f=fopen($path,'rb');if(!$f){http_response_code(503);exit;}fpassthru($f);fclose($f);
