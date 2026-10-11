"""Database validation shared by the packager and deployment helper."""
from datetime import datetime, timezone
import json
import re
REPORT_REVISION = '0.8.8'

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

def quoted(value):return '`'+value.replace('`','``')+'`'

def public_grants(grants):
    # SHOW GRANTS on MariaDB can include authentication hashes. The shared
    # report needs permission statements, not account authentication data.
    return '\n'.join(re.sub(r'\s+IDENTIFIED\b.*$', '',line,flags=re.I) for line in grants.splitlines())

def verify_database(stage,base,settings,query,run,db_command,write):
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
    if 'GRANT SELECT ON `oddb_v1`.*' not in grants or re.search(r'GRANT (?!USAGE|SELECT)',grants):issues.append('Unexpected web account grants.')
    php=run([*base,'exec','-T','web','php','--version'],capture=True)
    modules=run([*base,'exec','-T','web','php','-m'],capture=True).splitlines()
    if not all(name in modules for name in ['PDO','pdo_mysql','mbstring']):issues.append('Required PHP module missing.')
    php_files=sorted((stage/'app/public').rglob('*.php'))
    for file in php_files:
        target='/srv/oddb/app/public/'+file.relative_to(stage/'app/public').as_posix()
        run([*base,'exec','-T','web','php','-l',target],capture=True)
    report={'revision':REPORT_REVISION,'tested_at_utc':datetime.now(timezone.utc).isoformat(),'database_version':query(base,'SELECT VERSION();'),'php_version':php.strip(),'required_php_modules_present':all(n in modules for n in ['PDO','pdo_mysql','mbstring']),'php_syntax_files_passed':len(php_files),'table_counts':counts,'foreign_keys_checked':len(orphans),'orphan_checks':orphans,'views_checked_as_web_account':expected['views'],'web_grants':public_grants(grants),'issues':issues,'passed':not issues,'backup_sha256':settings['backup_sha256'],'browser_workflows_tested':False}
    write(stage/'runtime/verification_report.json',json.dumps(report,indent=2))
    if issues:raise ValueError('Deployment verification failed: '+', '.join(issues)+'. See runtime/verification_report.json.')
    print('Passed:',len(counts),'table counts,',len(orphans),'foreign-key orphan checks and',len(expected['views']),'views as oddb_web.',flush=True)
