#!/usr/bin/env python3
"""Prepare and optionally run a separate, local ODDB restoration test.
Python 3.9+. Docker/Compose required only with --start or --stop.
No XAMPP commands, host MySQL connections, source edits or DNS changes.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import time
from urllib.request import urlopen
from urllib.error import URLError

REVISION='0.8.7'
DATABASE='oddb_stage'
VIEW_DEFINER=re.compile(rb'^/\*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER \*/;?\r?\n?$')
DOCKERFILE='''FROM php:8.4-apache
RUN apt-get update && apt-get install -y --no-install-recommends libonig-dev \\
 && docker-php-ext-install pdo_mysql mbstring \\
 && a2enmod headers rewrite \\
 && rm -rf /var/lib/apt/lists/*
COPY apache.conf /etc/apache2/sites-available/000-default.conf
COPY php.ini /usr/local/etc/php/conf.d/oddb-staging.ini
'''
APACHE='''<VirtualHost *:80>
    ServerName localhost
    DocumentRoot /srv/oddb/app/public
    <Directory /srv/oddb/app/public>
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>
    ErrorLog /proc/self/fd/2
    CustomLog /proc/self/fd/1 combined
</VirtualHost>
'''
PHP_INI='''display_errors=Off
display_startup_errors=Off
log_errors=On
error_log=/proc/self/fd/2
expose_php=Off
memory_limit=256M
max_execution_time=120
post_max_size=20M
upload_max_filesize=20M
date.timezone=UTC
'''

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def write(path,content,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(content);path.chmod(mode)

def check_backup(export):
    metadata=json.loads((export/'review_metadata.json').read_text())
    if not metadata.get('full_export_created'):raise ValueError('The collector did not create a complete full export.')
    for group,key in [('events','events'),('routines','routines')]:
        info=metadata.get(group,{})
        if not info.get('definitions_exported') and not (info.get('inventory_verified') and info.get(key)==[]):
            raise ValueError('The full export may omit '+group+'. Resolve this before restoration.')
    checks={}
    for line in (export/'SHA256SUMS.txt').read_text().splitlines():
        digest,name=line.split('  ',1);checks[name]=digest
    for name in ['review_metadata.json','table_counts.tsv','oddb_v1_schema.sql.gz','oddb_v1_full.sql.gz']:
        print('Verifying',name,flush=True)
        if sha(export/name)!=checks.get(name):raise ValueError('Checksum mismatch: '+name)
    with gzip.open(export/'oddb_v1_full.sql.gz','rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):pass
    return metadata,checks['oddb_v1_full.sql.gz']

def parse_schema(schema):
    tables={};foreign_keys=[]
    for name,body in re.findall(r'CREATE TABLE `([^`]+)` \((.*?)\) ENGINE=',schema,re.S):
        indexes={}
        for line in body.splitlines():
            match=re.match(r'\s*(PRIMARY KEY|(?:UNIQUE )?KEY `([^`]+)`) \((.*)\),?$',line)
            if match:
                key=match.group(2) or 'PRIMARY'
                indexes[key]=[[col,int(prefix) if prefix else None] for col,prefix in re.findall(r'`([^`]+)`(?:\((\d+)\))?',match.group(3))]
        tables[name]={'columns':re.findall(r'^  `([^`]+)`',body,re.M),'indexes':indexes}
        for constraint,local,parent,remote in re.findall(r'CONSTRAINT `([^`]+)` FOREIGN KEY \(([^)]+)\) REFERENCES `([^`]+)` \(([^)]+)\)',body):
            foreign_keys.append({'name':constraint,'child':name,'local':re.findall(r'`([^`]+)`',local),'parent':parent,'remote':re.findall(r'`([^`]+)`',remote)})
    views=re.findall(r'/\*!50001 VIEW `([^`]+)` AS ',schema)
    return {'tables':tables,'foreign_keys':foreign_keys,'views':views}

def prepare(app,export,stage,port):
    if stage.exists():raise ValueError('Staging folder already exists. Use --resume to continue it, or choose another --stage-dir.')
    for parent in [app,app.parent/'retnet_pipeline/releases',export]:
        if stage==parent or stage.is_relative_to(parent):raise ValueError('Place staging outside your application, releases and export folder.')
    if not (app/'public/index.php').is_file():raise ValueError('The --app-dir folder must contain public/index.php.')
    metadata,backup_sha=check_backup(export)
    schema=gzip.open(export/'oddb_v1_schema.sql.gz','rt').read()
    expected=parse_schema(schema)
    counts={t['table']:t['exact_rows'] for t in metadata['tables'] if t['type']=='BASE TABLE'}
    if set(counts)!=set(expected['tables']):raise ValueError('Schema and table count inventory do not agree.')
    definitions=sum(bool(VIEW_DEFINER.fullmatch(line)) for line in schema.encode().splitlines(keepends=True))
    if definitions!=len(expected['views']):raise ValueError('Expected root-definer view format was not found for every view.')
    catalog=json.loads((app/'config/release_catalog.json').read_text())
    releases=[];release_root=(app.parent/'retnet_pipeline/releases').resolve()
    for item in catalog.get('files',[]):
        relative=Path(item['relative_path']);source=(app.parent/relative).resolve()
        if relative.is_absolute() or not source.is_relative_to(release_root) or not source.is_file():raise ValueError('Missing or invalid release file: '+str(relative))
        if source.stat().st_size!=item['size_bytes']:raise ValueError('Release file size differs from catalog: '+str(relative))
        releases.append((source,relative.relative_to('retnet_pipeline/releases')))
    print('Preparing a separate app copy and',len(releases),'release files...',flush=True)
    stage.mkdir(parents=True,mode=0o700);stage.chmod(0o700)
    staged_app=stage/'app';shutil.copytree(app/'public',staged_app/'public')
    write(staged_app/'config/release_catalog.json',json.dumps(catalog,indent=2),0o644)
    for source,relative in releases:
        target=stage/'releases'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);target.chmod(0o644)
    for folder in [staged_app,stage/'releases']:
        folder.chmod(0o755)
        for path in folder.rglob('*'):path.chmod(0o755 if path.is_dir() else 0o644)
    root_password=secrets.token_hex(32);web_password=secrets.token_hex(32)
    write(stage/'.env','ODDB_STAGE_ROOT_PASSWORD='+root_password+'\nODDB_STAGE_WEB_PASSWORD='+web_password+'\n')
    write(stage/'init/01-web-user.sql',"CREATE USER 'oddb_web'@'%' IDENTIFIED BY '"+web_password+"';\nGRANT SELECT ON `oddb_stage`.* TO 'oddb_web'@'%';\n",0o644)
    write(stage/'docker/Dockerfile',DOCKERFILE,0o644)
    write(stage/'docker/apache.conf',APACHE,0o644)
    write(stage/'docker/php.ini',PHP_INI,0o644)
    def mount(source,target):
        return {'type':'bind','source':str(source).replace('$','$$'),'target':target,'read_only':True,'bind':{'create_host_path':False}}
    compose={'services':{
        'db':{'image':'mariadb:11.4','environment':{'MARIADB_ROOT_PASSWORD':'${ODDB_STAGE_ROOT_PASSWORD:?Missing staging password}','MARIADB_ROOT_HOST':'localhost','MARIADB_DATABASE':DATABASE},'command':['--event-scheduler=OFF'],'volumes':[{'type':'volume','source':'db-data','target':'/var/lib/mysql'},mount(stage/'init/01-web-user.sql','/docker-entrypoint-initdb.d/01-web-user.sql')],'healthcheck':{'test':['CMD','healthcheck.sh','--connect','--innodb_initialized'],'interval':'5s','timeout':'5s','retries':48,'start_period':'20s'}},
        'web':{'build':{'context':str(stage/'docker').replace('$','$$')},'environment':{'ODDB_DB_HOST':'db','ODDB_DB_PORT':'3306','ODDB_DB_NAME':DATABASE,'ODDB_DB_USER':'oddb_web','ODDB_DB_PASSWORD':'${ODDB_STAGE_WEB_PASSWORD:?Missing staging password}'},'ports':['127.0.0.1:'+str(port)+':80'],'volumes':[mount(staged_app,'/srv/oddb/app'),mount(stage/'releases','/srv/oddb/retnet_pipeline/releases')],'depends_on':{'db':{'condition':'service_healthy'}}}
    },'volumes':{'db-data':{}}}
    write(stage/'compose.yaml',json.dumps(compose,indent=2),0o600)
    settings={'revision':REVISION,'project':'oddb-stage-'+secrets.token_hex(6),'port':port,'source_app':str(app),'export':str(export),'backup_sha256':backup_sha,'expected_counts':counts,'expected_schema':expected,'release_files':len(releases)}
    write(stage/'settings.json',json.dumps(settings,indent=2))
    shutil.copy2(Path(__file__).resolve(),stage/'run_staging.py');(stage/'run_staging.py').chmod(0o600)
    write(stage/'.gitignore','*\n')
    write(stage/'README.txt','''ODDB local staging test, v0.8.7
The original app, release files, backup and XAMPP database remain unchanged.
The app and release files are copies, served only on 127.0.0.1.
MariaDB has a separate Docker volume and no published database port.
The web database account has SELECT privileges only.
The four view security clauses are changed only in the import stream.
Credentials are in .env and init/01-web-user.sql beneath this private folder.
Share only staging_report.json, never this whole staging folder.

From this folder:
  python3 run_staging.py --resume --start
  python3 run_staging.py --resume --stop

--start preserves an existing import. It refuses to overwrite a partially
imported database. If import fails, keep restore.log for diagnosis. Do not
delete the volume to retry until you have reviewed the failure.
--stop stops this project's containers. It does not remove database data.

This is local staging, not public hosting. HTTPS, automated backups, dense
graph/compare timings, session restoration, filters, exports, mobile and
keyboard workflows still need verification before production.
''')
    print('Prepared staging folder:',stage,flush=True)
    return settings

def compose_command(stage,settings):
    return ['docker','compose','--env-file',str(stage/'.env'),'-p',settings['project'],'-f',str(stage/'compose.yaml')]

def runtime_environment():
    # Do not let unrelated shell passwords override this project's .env.
    return {k:v for k,v in os.environ.items() if k not in ['ODDB_STAGE_ROOT_PASSWORD','ODDB_STAGE_WEB_PASSWORD','COMPOSE_FILE','COMPOSE_PROJECT_NAME','COMPOSE_PROFILES']}

def run(command,capture=False):
    result=subprocess.run(command,env=runtime_environment(),text=True,capture_output=capture)
    if result.returncode:raise ValueError('Command failed: '+(' '.join(command[:3]))+((': '+result.stderr.strip()[:1500]) if capture else '. See the terminal output.'))
    return result.stdout if capture else ''

def db_command(base,user='root'):
    if user=='root':
        shell='export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"; exec mariadb --no-defaults --user=root --default-character-set=utf8mb4 --batch --raw --skip-column-names --database=oddb_stage "$@"'
        return [*base,'exec','-T','db','sh','-c',shell,'oddb-client']
    shell='export MYSQL_PWD="$ODDB_DB_PASSWORD"; exec php -r \'$p=new PDO("mysql:host=db;dbname=oddb_stage;charset=utf8mb4","oddb_web",getenv("MYSQL_PWD"),[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);$p->query($argv[1]);echo "OK";\' "$@"'
    return [*base,'exec','-T','web','sh','-c',shell,'oddb-client']

def query(base,sql):return run([*db_command(base),'--execute='+sql],capture=True).strip()

def quoted(value):return '`'+value.replace('`','``')+'`'

def restore(stage,base,settings):
    target=Path(settings['export'])/'oddb_v1_full.sql.gz'
    if sha(target)!=settings['backup_sha256']:raise ValueError('Backup changed since staging preparation.')
    if int(query(base,"SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE();")):
        raise ValueError('Staging database already contains objects. Refusing to overwrite it. If import previously completed, use its import_complete.json marker.')
    print('Restoring the backup into the separate oddb_stage container database...',flush=True)
    changed=0;log=stage/'restore.log'
    with log.open('wb') as output:
        process=subprocess.Popen(db_command(base),stdin=subprocess.PIPE,stdout=output,stderr=output,env=runtime_environment())
        try:
            try:
                with gzip.open(target,'rb') as dump:
                    for line in dump:
                        if VIEW_DEFINER.fullmatch(line):
                            line=b'/*!50013 SQL SECURITY INVOKER */\n';changed+=1
                        process.stdin.write(line)
                process.stdin.close()
            except BrokenPipeError:
                try:process.stdin.close()
                except BrokenPipeError:pass
            status=process.wait()
            if status:raise ValueError('Staging import failed. Details are in '+str(log))
        finally:
            if not process.stdin.closed:process.stdin.close()
            if process.poll() is None:process.kill();process.wait()
    if changed!=len(settings['expected_schema']['views']):raise ValueError('Unexpected number of view definer replacements. Review restore.log and the staged schema.')
    write(stage/'import_complete.json',json.dumps({'backup_sha256':settings['backup_sha256'],'views_adjusted':changed}))

def verify(stage,base,settings):
    print('Verifying exact counts, columns, indexes, foreign keys and views...',flush=True)
    expected=settings['expected_schema'];counts=[];issues=[]
    actual_names=query(base,"SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME;").splitlines()
    if set(actual_names)!=set(expected['tables']):issues.append('Base table inventory differs.')
    engines=query(base,"SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME;")
    if any(line.split('\t')[1]!='InnoDB' for line in engines.splitlines()):issues.append('Unexpected table engine.')
    for name,info in expected['tables'].items():
        actual=int(query(base,'SELECT COUNT(*) FROM '+quoted(name)+';'));want=settings['expected_counts'][name]
        counts.append({'table':name,'expected':want,'actual':actual,'passed':actual==want})
        if actual!=want:issues.append('Count differs: '+name)
        cols=query(base,"SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='"+name+"' ORDER BY ORDINAL_POSITION;").splitlines()
        if cols!=info['columns']:issues.append('Columns differ: '+name)
        data=query(base,"SELECT INDEX_NAME,COLUMN_NAME,COALESCE(SUB_PART,0) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='"+name+"' ORDER BY INDEX_NAME,SEQ_IN_INDEX;")
        indexes={}
        for line in data.splitlines():
            key,col,prefix=line.split('\t');indexes.setdefault(key,[]).append([col,int(prefix) or None])
        if indexes!=info['indexes']:issues.append('Indexes differ: '+name)
        print('Checked',name+':',actual,'rows (expected',str(want)+').',flush=True)
    actual_fk=query(base,"SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_TYPE='FOREIGN KEY' ORDER BY CONSTRAINT_NAME;").splitlines()
    if set(actual_fk)!={x['name'] for x in expected['foreign_keys']}:issues.append('Foreign key inventory differs.')
    orphans=[]
    for fk in expected['foreign_keys']:
        join=' AND '.join('c.'+quoted(c)+'=p.'+quoted(p) for c,p in zip(fk['local'],fk['remote']))
        present=' AND '.join('c.'+quoted(c)+' IS NOT NULL' for c in fk['local'])
        sql='SELECT COUNT(*) FROM '+quoted(fk['child'])+' c LEFT JOIN '+quoted(fk['parent'])+' p ON '+join+' WHERE '+present+' AND p.'+quoted(fk['remote'][0])+' IS NULL;'
        count=int(query(base,sql));orphans.append({'constraint':fk['name'],'orphan_rows':count})
        if count:issues.append('Orphan rows: '+fk['name'])
        if len(orphans)%10==0:print('Foreign-key relationships checked:',len(orphans),'of',len(expected['foreign_keys']),flush=True)
    views=query(base,"SELECT TABLE_NAME,SECURITY_TYPE FROM information_schema.VIEWS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME;")
    view_rows=[line.split('\t') for line in views.splitlines()]
    if {x[0] for x in view_rows}!=set(expected['views']) or any(x[1]!='INVOKER' for x in view_rows):issues.append('View inventory or security policy differs.')
    for view in expected['views']:run([*db_command(base,'web'),'SELECT * FROM '+quoted(view)+' LIMIT 1;'],capture=True)
    grants=query(base,"SHOW GRANTS FOR 'oddb_web'@'%';")
    if 'GRANT SELECT ON `oddb_stage`.*' not in grants or re.search(r'GRANT (?!USAGE|SELECT)',grants):issues.append('Unexpected web account grants.')
    php=run([*base,'exec','-T','web','php','--version'],capture=True)
    modules=run([*base,'exec','-T','web','php','-m'],capture=True).splitlines()
    if not all(name in modules for name in ['PDO','pdo_mysql','mbstring']):issues.append('Required PHP module missing.')
    php_files=sorted((stage/'app/public').rglob('*.php'))
    for file in php_files:
        target='/srv/oddb/app/public/'+file.relative_to(stage/'app/public').as_posix()
        run([*base,'exec','-T','web','php','-l',target],capture=True)
    report={'revision':REVISION,'tested_at_utc':datetime.now(timezone.utc).isoformat(),'database_version':query(base,'SELECT VERSION();'),'php_version':php.strip(),'required_php_modules_present':all(n in modules for n in ['PDO','pdo_mysql','mbstring']),'php_syntax_files_passed':len(php_files),'table_counts':counts,'foreign_keys_checked':len(orphans),'orphan_checks':orphans,'views_checked_as_web_account':expected['views'],'web_grants':grants,'issues':issues,'passed':not issues,'backup_sha256':settings['backup_sha256'],'browser_workflows_tested':False}
    write(stage/'staging_report.json',json.dumps(report,indent=2))
    if issues:raise ValueError('Staging verification failed: '+', '.join(issues)+'. See staging_report.json.')
    print('Passed:',len(counts),'table counts,',len(orphans),'foreign-key orphan checks and',len(expected['views']),'views as oddb_web.',flush=True)

def start(stage,settings):
    if not shutil.which('docker'):raise ValueError('Docker is not on PATH.')
    run(['docker','info'],capture=True);base=compose_command(stage,settings)
    run([*base,'config','--quiet'],capture=True)
    port=settings['port']
    # Only test bind availability before creating the web container.
    cid=run([*base,'ps','-q','web'],capture=True).strip()
    if not cid:
        with socket.socket() as sock:
            try:sock.bind(('127.0.0.1',port))
            except OSError:raise ValueError('Local port '+str(port)+' is busy. Prepare a new stage folder using --port.')
    print('Starting the separate MariaDB 11.4 service...',flush=True)
    run([*base,'up','-d','--wait','--wait-timeout','300','db'])
    marker=stage/'import_complete.json'
    if marker.exists():
        if json.loads(marker.read_text())['backup_sha256']!=settings['backup_sha256']:raise ValueError('Staging import marker does not match backup.')
        print('Using the existing staging import. No data will be overwritten.',flush=True)
    else:restore(stage,base,settings)
    print('Building and starting PHP 8.4 / Apache...',flush=True)
    run([*base,'up','-d','--build','web'])
    verify(stage,base,settings)
    url='http://127.0.0.1:'+str(port)+'/'
    print('Checking the Home page and read-only APIs...',flush=True)
    checks={};failure=None
    for route in ['', 'api/stats.php','api/release.php']:
        attempts=15 if not route else 1
        for attempt in range(attempts):
            try:
                with urlopen(url+route,timeout=10 if not route else 180) as response:
                    body=response.read();status=response.status
                if route and json.loads(body).get('ok') is not True:raise ValueError('API returned ok=false: '+route)
                checks[route or 'Home']={'status':status,'bytes':len(body)};break
            except (URLError,ValueError,TimeoutError) as error:
                if attempt==attempts-1:failure=str(error);break
                time.sleep(2)
        if failure:break
    report=json.loads((stage/'staging_report.json').read_text());report['http_checks']=checks
    if failure:report['issues'].append('HTTP smoke check: '+failure);report['passed']=False
    write(stage/'staging_report.json',json.dumps(report,indent=2))
    if failure:raise ValueError('HTTP smoke check failed. See staging_report.json and Docker web logs.')
    print('Staging test passed. Open:',url,flush=True)
    print('Send for review:',stage/'staging_report.json',flush=True)
    print('Stop later: python3 '+str(stage/'run_staging.py')+' --resume --stop',flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-dir',type=Path,default=Path.cwd())
    parser.add_argument('--export-dir',type=Path,default=Path.home()/'ODDB_deployment_review_20261008T131337804444Z')
    default_stage=Path(__file__).resolve().parent if Path(__file__).name=='run_staging.py' else Path.home()/'ODDB_staging_v0.8.7'
    parser.add_argument('--stage-dir',type=Path,default=default_stage)
    parser.add_argument('--port',type=int,default=8082)
    parser.add_argument('--resume',action='store_true')
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--start',action='store_true');mode.add_argument('--stop',action='store_true')
    args=parser.parse_args();os.umask(0o077)
    if not 1024<=args.port<=65535:raise ValueError('Choose a port between 1024 and 65535.')
    stage=args.stage_dir.expanduser().resolve()
    print('ODDB local staging helper v'+REVISION,flush=True)
    if args.resume:
        settings=json.loads((stage/'settings.json').read_text())
        if settings.get('revision')!=REVISION or not re.fullmatch(r'oddb-stage-[a-f0-9]{12}',settings.get('project','')):raise ValueError('Invalid staging settings.')
    else:
        if args.stop:raise ValueError('Use --resume --stop to stop an existing stage.')
        settings=prepare(args.app_dir.expanduser().resolve(),args.export_dir.expanduser().resolve(),stage,args.port)
    if args.stop:run([*compose_command(stage,settings),'stop']);print('Staging containers stopped. Database data retained.')
    elif args.start:start(stage,settings)
    else:print('Prepared only. Start with: python3 '+str(stage/'run_staging.py')+' --resume --start')

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,subprocess.SubprocessError,BrokenPipeError) as error:
        raise SystemExit('Staging stopped: '+str(error))
