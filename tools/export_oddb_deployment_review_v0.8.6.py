#!/usr/bin/env python3
"""Export ODDB for deployment review without changing application or database data.
Run from your app folder: python3 export_oddb_deployment_review_v0.8.6.py
Python 3.9+, standard library only. XAMPP defaults match your local setup.
Revision v0.8.6c handles event error 1577 and routine-table error 1558 read-only.
"""
import argparse
from datetime import datetime, timezone
import getpass
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

def find_binary(directory, names):
    for name in names:
        candidate=directory/name
        if candidate.is_file(): return str(candidate)
    for name in names:
        candidate=shutil.which(name)
        if candidate: return candidate
    raise ValueError('Missing tool: '+', '.join(names)+'. Check --bin-dir.')

def run(command):
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or 'A local check failed.')
    return result.stdout.strip()

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def inspect_events(query, version):
    scheduler=query('SELECT @@event_scheduler;').strip().upper()
    result={'scheduler':scheduler,'inventory_verified':False,'definitions_exported':False,'events':[],'inspection_errors':[]}
    # MariaDB's SHOW EVENTS can fail with 1577 when the scheduler is DISABLED.
    # Inspect event metadata read-only; do not enable the scheduler or run events.
    queries=["SELECT EVENT_NAME,STATUS FROM information_schema.EVENTS WHERE EVENT_SCHEMA=DATABASE() ORDER BY EVENT_NAME;"]
    if 'mariadb' in version.lower():
        queries.insert(0,"SELECT name,status FROM mysql.event WHERE db=DATABASE() ORDER BY name;")
    for sql in queries:
        try:
            inventory=query(sql)
            result['events']=[dict(zip(['name','status'],line.split('\t'))) for line in inventory.splitlines() if line]
            result['inventory_verified']=True
            break
        except ValueError as error:
            result['inspection_errors'].append(str(error))
    result['dump_events']=scheduler!='DISABLED'
    result['complete_possible']=result['dump_events'] or (result['inventory_verified'] and not result['events'])
    return result

def inspect_routines(query,version):
    result={'inventory_verified':False,'definitions_exported':False,'routines':[],'inspection_errors':[],'dump_routines':True,'complete_possible':True}
    queries=["SELECT ROUTINE_NAME,ROUTINE_TYPE FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=DATABASE() ORDER BY ROUTINE_NAME,ROUTINE_TYPE;"]
    if 'mariadb' in version.lower():
        queries.insert(0,"SELECT name,type FROM mysql.proc WHERE db=DATABASE() ORDER BY name,type;")
    for sql in queries:
        try:
            inventory=query(sql)
            result['routines']=[dict(zip(['name','type'],line.split('\t'))) for line in inventory.splitlines() if line]
            result['inventory_verified']=True
            break
        except ValueError as error:
            result['inspection_errors'].append(str(error))
    return result

def dump(command,path):
    # Keep memory bounded even for the large variant tables.
    temporary=path.with_suffix(path.suffix+'.partial')
    try:
        with tempfile.TemporaryFile() as errors:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=errors)
            try:
                with gzip.open(temporary,'wb',compresslevel=6) as output:
                    shutil.copyfileobj(process.stdout,output,1024*1024)
                status=process.wait()
                errors.seek(0);messages=errors.read().decode('utf-8',errors='replace').strip()
                if status:raise ValueError('Database export failed: '+messages)
                if temporary.stat().st_size<32:raise ValueError('The export is unexpectedly empty.')
                os.replace(temporary,path)
            finally:
                process.stdout.close()
                if process.poll() is None:process.kill();process.wait()
        return messages
    finally:
        if temporary.exists():temporary.unlink()

def dump_with_metadata(command,path,events,routines,require_complete=False):
    # Each known failure disables one option, allowing at most two retries.
    while True:
        try:
            return dump(command,path)
        except ValueError as error:
            message=str(error);lower=message.lower()
            if events['dump_events'] and '1577' in message and 'show events' in lower:
                events['dump_event_error']=message
                events['dump_events']=False
                events['definitions_exported']=False
                events['complete_possible']=events['inventory_verified'] and not events['events']
                flags=('--events','--skip-events');replacement='--skip-events'
                print('SHOW EVENTS failed with error 1577. Retrying with --skip-events.',flush=True)
            elif routines['dump_routines'] and '1558' in message and 'mysql.proc' in lower and ('show function status' in lower or 'show procedure status' in lower):
                routines['dump_routine_error']=message
                routines['system_table_upgrade_required']=True
                routines['dump_routines']=False
                routines['definitions_exported']=False
                routines['complete_possible']=routines['inventory_verified'] and not routines['routines']
                flags=('--routines','--skip-routines');replacement='--skip-routines'
                print('Routine system table failed with error 1558. Retrying with --skip-routines; no server changes are made.',flush=True)
            else:
                raise
            if require_complete and not (events['complete_possible'] and routines['complete_possible']):
                print('Full backup skipped because event or routine definitions cannot be included.',flush=True)
                return None
            retry=[option for option in command[:-1] if option not in flags]
            command=[*retry,replacement,command[-1]]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-dir',type=Path,default=Path.cwd())
    parser.add_argument('--bin-dir',type=Path,default=Path('/opt/lampp/bin'))
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=3306)
    parser.add_argument('--database',default='oddb_v1')
    parser.add_argument('--user',default='root')
    parser.add_argument('--ask-password',action='store_true')
    parser.add_argument('--schema-only',action='store_true')
    parser.add_argument('--output-parent',type=Path,default=Path.home())
    args=parser.parse_args()
    print('ODDB deployment review helper v0.8.6c',flush=True)
    app=args.app_dir.expanduser().resolve();public=app/'public'
    if not (public/'index.php').is_file():raise ValueError('Run in your ODDB app folder, or use --app-dir.')
    parent=args.output_parent.expanduser().resolve()
    if parent==public.resolve() or parent.is_relative_to(public.resolve()):
        raise ValueError('Choose an export location outside the public website folder.')
    if not 1<=args.port<=65535:raise ValueError('Invalid database port.')
    mysql=find_binary(args.bin_dir,['mysql','mariadb'])
    dump_bin=find_binary(args.bin_dir,['mysqldump','mariadb-dump'])
    php=find_binary(args.bin_dir,['php'])
    os.umask(0o077)
    output=parent/('ODDB_deployment_review_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(parents=True,exist_ok=False)
    print('Export folder:',output,flush=True)
    print('Keep database imports and schema changes paused while this runs.',flush=True)
    password=getpass.getpass('Local database password: ') if args.ask_password else ''
    with tempfile.TemporaryDirectory(prefix='oddb-db-client-') as private:
        config=Path(private)/'client.cnf'
        escaped=password.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r')
        config.write_text('[client]\npassword="'+escaped+'"\n');config.chmod(0o600)
        # Read only our private password file. Other client option files must
        # not introduce implicit dump options into this read-only export.
        connection=['--defaults-file='+str(config),'--protocol=TCP','--host='+args.host,'--port='+str(args.port),'--user='+args.user,'--default-character-set=utf8mb4']
        def query(sql):return run([mysql,*connection,'--batch','--raw','--skip-column-names','--database='+args.database,'--execute='+sql])
        version=query('SELECT VERSION(), @@version_comment, @@character_set_server, @@collation_server;')
        events=inspect_events(query,version)
        routines=inspect_routines(query,version)
        print('Reported event scheduler:',events['scheduler'],flush=True)
        inventory=query("SELECT TABLE_NAME,TABLE_TYPE,COALESCE(ENGINE,''),COALESCE(TABLE_ROWS,0),COALESCE(DATA_LENGTH,0)+COALESCE(INDEX_LENGTH,0) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME;")
        tables=[]
        for line in inventory.splitlines():
            name,kind,engine,estimated,size=line.split('\t')
            tables.append({'table':name,'type':kind,'engine':engine,'estimated_rows':int(estimated),'bytes':int(size)})
        if not tables:raise ValueError('The selected database has no tables or views.')
        count_lines=[]
        print('Collecting exact table counts...',flush=True)
        for table in tables:
            if table['type']!='BASE TABLE':continue
            quoted='`'+table['table'].replace('`','``')+'`'
            table['exact_rows']=int(query('SELECT COUNT(*) FROM '+quoted+';'))
            count_lines.append(table['table']+'\t'+str(table['exact_rows']))
        (output/'table_counts.tsv').write_text('table\texact_rows\n'+'\n'.join(count_lines)+'\n')
        flags=['--quick','--hex-blob','--triggers','--no-tablespaces']
        if not events['dump_events']:
            print('Event scheduler is DISABLED. Exporting without --events; server settings remain unchanged.',flush=True)
            if events['inventory_verified'] and not events['events']:
                print('Verified: this database has no scheduled events to export.',flush=True)
            else:
                print('Event definitions need separate review. The full backup will be skipped; the review ZIP will still be created.',flush=True)
        print('Exporting schema, routines and triggers...',flush=True)
        event_flag='--events' if events['dump_events'] else '--skip-events'
        routine_flag='--routines' if routines['dump_routines'] else '--skip-routines'
        schema_messages=dump_with_metadata([dump_bin,*connection,*flags,'--no-data','--skip-lock-tables',event_flag,routine_flag,args.database],output/'oddb_v1_schema.sql.gz',events,routines)
        events['definitions_exported']=events['dump_events']
        routines['definitions_exported']=routines['dump_routines']
        nontransactional=[t['table'] for t in tables if t['type']=='BASE TABLE' and t['engine'].lower()!='innodb']
        exported=False;data_messages=''
        if not args.schema_only and not nontransactional and events['complete_possible'] and routines['complete_possible']:
            print('Exporting schema and data with a transactional snapshot...',flush=True)
            event_flag='--events' if events['dump_events'] else '--skip-events'
            routine_flag='--routines' if routines['dump_routines'] else '--skip-routines'
            data_messages=dump_with_metadata([dump_bin,*connection,*flags,'--single-transaction',event_flag,routine_flag,args.database],output/'oddb_v1_full.sql.gz',events,routines,require_complete=True)
            exported=data_messages is not None
            if data_messages is None:data_messages='Full dump skipped: event or routine definitions could not be exported.'
        elif nontransactional:
            print('Full dump skipped because some tables are not InnoDB. Send the review bundle first:',', '.join(nontransactional),flush=True)
        elif not args.schema_only and not (events['complete_possible'] and routines['complete_possible']):
            print('Full backup skipped because omitted events or routines exist, or their absence cannot be verified. The review ZIP will still be created.',flush=True)
    print('Checking PHP syntax and modules...',flush=True)
    php_version=run([php,'--version']);modules=run([php,'-m']).splitlines()
    lints=[]
    for file in sorted(public.rglob('*.php')):
        result=subprocess.run([php,'-l',str(file)],capture_output=True,text=True)
        lints.append({'file':str(file.relative_to(app)),'passed':result.returncode==0,'output':(result.stdout+result.stderr).strip()})
    release=[];catalog=app/'config/release_catalog.json'
    if catalog.is_file():
        for entry in json.loads(catalog.read_text()).get('files',[]):
            relative=str(entry.get('relative_path',''));candidate=(app.parent/relative).resolve()
            allowed=(app.parent/'retnet_pipeline/releases').resolve()
            valid=bool(relative) and candidate.is_relative_to(allowed)
            exists=valid and candidate.is_file()
            release.append({'relative_path':relative,'present':exists,'actual_size_bytes':candidate.stat().st_size if exists else None,'catalog_size_bytes':entry.get('size_bytes')})
    metadata={'collector_revision':'0.8.6c','database':args.database,'server_version':version,'dump_client_version':run([dump_bin,'--version']),'php_version':php_version,'php_modules':modules,'required_modules_present':{name:any(x.lower()==name.lower() for x in modules) for name in ['PDO','pdo_mysql','mbstring']},'tables':tables,'events':events,'routines':routines,'nontransactional_tables':nontransactional,'full_export_created':exported,'schema_export_messages':schema_messages,'full_export_messages':data_messages,'php_lint':lints,'release_files':release,'notes':['Table counts were collected before the dump. Pause writes so counts can be compared after restoration.','A successful dump is not a verified restoration.','If event or routine export is disabled, those definitions are excluded from the schema dump. The metadata records whether their absence was verified and any system-table upgrade error.','The full SQL export is a database copy. Keep it outside GitHub and the public website.','Database account passwords and the mysql system database are not exported. Routine/view definers may contain account names.']}
    (output/'review_metadata.json').write_text(json.dumps(metadata,indent=2))
    zip_path=output/'ODDB_review_bundle.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as bundle:
        for name in ['review_metadata.json','table_counts.tsv','oddb_v1_schema.sql.gz']:bundle.write(output/name,name)
    files=[output/'review_metadata.json',output/'table_counts.tsv',output/'oddb_v1_schema.sql.gz',zip_path]
    if exported:files.append(output/'oddb_v1_full.sql.gz')
    (output/'SHA256SUMS.txt').write_text(''.join(sha(file)+'  '+file.name+'\n' for file in files))
    failed=[x['file'] for x in lints if not x['passed']]
    print('PHP syntax failures:',len(failed),'Missing required modules:',[x for x,ok in metadata['required_modules_present'].items() if not ok])
    print('Missing release files:',sum(not x['present'] for x in release),'of',len(release))
    print('Upload for review:',zip_path)
    if exported:print('Keep this full backup for server migration:',output/'oddb_v1_full.sql.gz')
    print('This tool did not import SQL or modify your website.')

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,subprocess.SubprocessError) as error:raise SystemExit('Export stopped: '+str(error))
