# Acceptance checks before DNS migration

Run `python3 ops/manage.py verify` after importing the database. This checks
every exported table count and column/index inventory, foreign-key orphans,
views with the read-only web account, PHP modules and syntax, release files,
and Home / statistics / release API responses. It writes a local report.

Then test the browser workflows through localhost or an SSH tunnel:

1. Home navigation, the short eye intro and all Browse categories.
2. Small and dense Explore graphs: search, expand, pan, zoom and reset.
3. Evidence filters, disease and drug comparisons, and path finding.
4. Saved-session restoration with matching graph and filter state.
5. SVG, PNG and tabular exports with the selected filters applied.
6. Every download listed in the release inventory.
7. Mobile layout and keyboard navigation with Tab, Enter and Escape.
8. Production error responses: provoke a database connection failure in a
   separate test instance, never the live database. Responses should contain a
   generic error and no password, SQL details or internal filesystem paths.

Measure dense graphs and comparison queries with representative concurrent
users. The packaging checks do not prove adequate memory, latency or capacity.
Verify HTTPS, HTTP-to-HTTPS redirects, a backup and a restore into a separate
empty test database before public release.
