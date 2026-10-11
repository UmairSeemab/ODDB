# Publication and reproducibility

Repository: https://github.com/UmairSeemab/ODDB

Suggested Data and Code Availability wording, after the source is uploaded:

"The ODDB application source and data preparation scripts are available at
https://github.com/UmairSeemab/ODDB. The analysis used repository release
[INSERT ACTUAL RELEASE TAG OR COMMIT]. The research website is available at
https://www.oculardiseases.fi/."

Replace the bracketed text with the actual version. If a manuscript DOI,
software archive DOI or dataset DOI exists, add its real identifier. This
package does not invent a publication, DOI, release tag or acceptance date.
Review the author list in CITATION.cff before publication.

## Licenses

Original ODDB software is distributed under the MIT License (see LICENSE).

This software license does not automatically grant permission to
redistribute upstream datasets, third-party figures or other externally
licensed materials. Their respective terms must be followed.

## What is reproducible from this repository

The repository includes the current app, current exported schema, table counts,
pipeline scripts and their existing requirements, web taxonomy scripts and
migrations, curated mapping files and available source manifests. The runtime
uses PHP 8.4 and MariaDB 11.4. Container tags track these version series, so
record image digests for the final publication deployment.

Raw source downloads, intermediate tables, historical UI patches and backups
are not part of the source repository. Full pipeline reproduction requires the
original source files and their permissions. The release inventory records the
exact downloadable files and SHA-256 hashes. Those datasets and the full SQL
snapshot belong in the deployment package or a separately versioned research
data archive. A public archive location has not been supplied to this packager.
An empty schema alone does not reproduce the curated database.

Do not rerun old migrations on the imported full snapshot. It already includes
the web taxonomy and later database changes.

## Upload sequence

Keep the existing GitHub Pages site until the new server is ready. Create an
isolated branch or a fresh clone for the prepared source files. Do not overlay
the new source onto old tracked website files without reviewing removals.
This package intentionally contains no CNAME and does not publish via Pages.
The PHP application must run on cPouta or another PHP-capable host.

Inspect `git diff --cached` and the package inventory before committing. After
testing, create a real release tag and archive that release for your manuscript.
The packager neither uploads nor modifies the remote repository or DNS.
