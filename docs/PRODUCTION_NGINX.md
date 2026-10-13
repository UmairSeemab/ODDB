# ODDB v1: CSC cPouta production deployment

## Production architecture

- Public website: https://oculardiseases.fi
- Server: CSC cPouta, Ubuntu 24.04
- Public IPv4: 86.50.22.188
- Reverse proxy: host Nginx 1.24
- TLS: Let's Encrypt via Certbot
- Application: PHP 8.4 / Apache in Docker
- Local application endpoint: 127.0.0.1:8082
- Database: MariaDB 11.4 in Docker, without a public DB port
- Persistent database directory: /srv/oddb/database
- Automated database backup: daily at 02:30 UTC
- Off-server backup storage: CSC Allas

The GitHub source package does not contain the complete database,
private credentials, TLS private keys or production backup archives.

The distributed Compose configuration may use a named database volume.
Production uses a bind mount at /srv/oddb/database. Preserve this
difference when reconstructing the deployment.

## Nginx configuration

An initial HTTP reverse-proxy template is provided at:

deploy/nginx/oddb.conf.example

On an initial deployment, enable the site in Nginx and validate
the configuration before requesting certificates.

Do not overwrite the existing production Nginx configuration.

## HTTPS activation

Both DNS names must resolve to the server, and inbound TCP 80
and 443 must be permitted.

With Nginx and the Certbot Nginx plugin installed:

    sudo nginx -t
    sudo certbot --nginx \
      -d oculardiseases.fi \
      -d www.oculardiseases.fi \
      --redirect

Validate:

    curl -I https://oculardiseases.fi
    curl -I https://www.oculardiseases.fi
    sudo certbot renew --dry-run

Automatic renewal is provided by the enabled Certbot snap timer.

## Docker application

Production web traffic is forwarded by Nginx to:

    http://127.0.0.1:8082

The database does not expose port 3306 publicly.

The optional Caddy service in compose.yaml is not used by
the current production deployment.

IMPORTANT: Do not run `ops/manage.py publish` while host Nginx
occupies ports 80 and 443. That command starts the optional
Caddy proxy and causes a port conflict.

## Backup and recovery

Production uses the systemd unit oddb-backup.service and the
timer oddb-backup.timer, scheduled for 02:30 UTC.

The server-side operational scripts upload and verify SQL
backups in CSC Allas and prune eligible local backups.
These host-specific scripts and timers are installed
separately from the GitHub source package.

The local cleanup policy retains backups younger than
30 days and preserves at least the three newest backups.
Remote Allas retention is managed separately.

An isolated MariaDB recovery test was completed in October 2026.
The restored database passed:

- Exact counts for all 36 base tables
- All 50 foreign-key integrity checks
- Query tests for all four database views

Never test restoration against the live production database.

## Verification

From the production deployment directory:

    sudo docker compose ps
    sudo python3 ops/manage.py verify
    sudo systemctl status oddb-backup.timer
    sudo certbot certificates

Production deployment and certificate management are independent
of GitHub Pages. GitHub hosts the application source code.
