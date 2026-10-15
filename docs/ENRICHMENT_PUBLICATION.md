# Enriched deployment and publication notes

The source archive intentionally excludes full SQL data, downloadable research files, geolocation ranges, mail/database credentials, TLS keys, visitor records, raw logs, container images, runtime patch backups and private deployment state.

Keep matching data in a separately reviewed scientific archive with source attribution, version, checksums and applicable permissions. Supply all current release-catalog paths and statistics snapshots before acceptance testing. A schema-only database will not reproduce the live website data.

Deployment adaptations: web app env uses ODDB_DB_HOST, ODDB_DB_PORT, ODDB_DB_NAME, ODDB_DB_USER, ODDB_DB_PASSWORD. Configure a private mail password file if contact mail is enabled. Retain historical downloads at /srv/oddb/retnet_pipeline/releases and mount the enriched published download directory read-only at /srv/oddb/enrichment_downloads. Do not expose app/config as the document root.

Visitor service uses a private shared token (ANALYTICS_TOKEN in the sidecar and ODDB_VISITOR_TOKEN in web), /data for private aggregate/dedup SQLite and /geo for the licensed country lookup (ANALYTICS_GEO=/geo). Web uses ODDB_VISITOR_URL, ODDB_VISITOR_MODE and explicitly trusted ODDB_VISITOR_TRUSTED_PROXIES. Collection must stay off in preview. Preserve DB-IP Lite attribution and provide independently obtained country data plus import tooling before enabling country lookup. Never publish a live token or visitor SQLite file.

The earlier repository deployment files are preserved for provenance, not certified as a runnable enriched deployment. The private hosting handover contains exact runtime configuration and must stay separate from publication. Prepare and browser-test deployment adaptations on a separate host before moving DNS.

After upload, regenerate a final release/tag from the reviewed repository tree, preserve authors and license, and archive the matching permitted dataset separately. Historical checksums were replaced by the new source manifest, not presented as checksums for the current release. Browser behavior and a clean-host deployment still need review; packaging does not claim these tests passed.
