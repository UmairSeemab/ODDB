# cPouta deployment

The package is prepared for deployment, not evidence of a successful public
deployment. Install Docker Engine with the Compose plugin and Python 3 on the
VM. Docker and system packages are not bundled. Keep the VM security updates
and a documented administrator assignment in place.

## Copy and initialize

Copy the complete `ODDB_cpouta` folder using SSH/SFTP. For example, on your PC:

```bash
scp -r "$HOME/ODDB_cpouta" ubuntu@YOUR_FLOATING_IP:~/
```

Replace the example account and IP with your actual VM details. On the VM:

```bash
cd "$HOME/ODDB_cpouta"
python3 ops/manage.py init
python3 ops/manage.py restore
python3 ops/manage.py verify
```

If your account cannot access Docker, use `sudo python3 ops/manage.py restore`
and `sudo python3 ops/manage.py verify` from this same directory. The helper
resolves paths from its own location, not sudo's HOME.

`init` generates private passwords and a SELECT-only database user. `restore`
starts only the database, refuses a nonempty database, checks the snapshot
checksum, imports it into a separate named Docker volume, checks counts and
foreign keys, and then starts PHP. It converts only the exported root-definer
view clauses to SQL SECURITY INVOKER during import. It leaves the original
backup unchanged. An interrupted import is preserved for investigation and
cannot be overwritten by rerunning restore.

Only PHP's public directory is served. Config, pipeline data, SQL snapshots and
credentials are outside the document root. MariaDB has no published host port.
The PHP test port binds to 127.0.0.1:8082. To access it from your PC:

```bash
ssh -L 18082:127.0.0.1:8082 ubuntu@YOUR_FLOATING_IP
```

Open http://127.0.0.1:18082/ on your PC. Follow docs/TESTING.md.

## Public HTTPS and DNS

Keep the current GitHub Pages website available until acceptance tests pass.
Attach and retain the server's floating IP. Allow inbound TCP 80 and 443 in
the cPouta security group. Limit SSH (22) to approved administrator networks.
Do not open port 3306 or 8082 to the internet.

Ask university IT to update the apex and www records to the floating IP and
remove conflicting GitHub Pages CNAME/A records and obsolete AAAA records if
the new host has no IPv6 service. This changes records, not domain ownership
or nameservers. Both names in .env must resolve to this server for HTTPS.

After acceptance and DNS have been coordinated:

```bash
python3 ops/manage.py publish
```

Caddy exposes TCP 80/443 and obtains/renews HTTPS certificates when DNS and
network access meet its requirements. Certificate state lives in named Docker
volumes. The default names are oculardiseases.fi and www.oculardiseases.fi.
`publish` verifies the import marker and table/FK/view checks before starting
the proxy. Do not invoke it until you intend the site to be public.

```bash
python3 ops/manage.py stop
```

This stops only this Compose project. It does not delete volumes or data.

## Backups and updates

```bash
python3 ops/manage.py backup
```

This writes a transactional compressed dump, table counts and a SHA-256 file
under backups/. Copy it to independent storage and test recovery regularly.
Schedule the command using your VM's scheduler; no scheduled job is installed
by the package. Keep backups outside the web document root and GitHub.

Updates require a fresh package or reviewed source changes, a backup and
validation. Image tags track PHP 8.4, MariaDB 11.4 and Caddy 2; record digests and
test upgrades before deploying them. A single VM is not a high-availability
deployment.

## Official references

- cPouta: https://docs.csc.fi/cloud/pouta/
- Docker on Ubuntu: https://docs.docker.com/engine/install/ubuntu/
- PHP image: https://hub.docker.com/_/php
- MariaDB image: https://hub.docker.com/_/mariadb
- Caddy HTTPS: https://caddyserver.com/docs/automatic-https
