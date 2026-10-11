-- ODDB v1 final relational schema
-- Target: MySQL 8.x / MariaDB 10.4+ (XAMPP-compatible)
-- Character set: utf8mb4
--
-- Principles:
--  * stable ODDB/HGNC/NCT identifiers are primary/natural keys where available
--  * disease-drug therapeutic evidence is separate from drug-target pharmacology
--  * target-overlap is discovery context, never automatically therapeutic evidence
--  * drug forms/salts remain explicit entities
--  * source provenance and the complete original TSV row are preserved
--
-- Recommended invocation:
--   mysql -u root -p < oddb_v1_schema.sql

CREATE DATABASE IF NOT EXISTS oddb_v1
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE oddb_v1;

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS oddb_release (
    release_key                 VARCHAR(128) PRIMARY KEY,
    release_type                VARCHAR(64) NOT NULL,
    release_path                TEXT NOT NULL,
    manifest_filename           VARCHAR(255) NULL,
    manifest_sha256             CHAR(64) NULL,
    status                      VARCHAR(32) NOT NULL DEFAULT 'loaded',
    loaded_at                   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes                       TEXT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS oddb_import_log (
    import_log_id               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    release_key                 VARCHAR(128) NOT NULL,
    table_name                  VARCHAR(128) NOT NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_rows                 BIGINT UNSIGNED NOT NULL,
    inserted_rows               BIGINT UNSIGNED NOT NULL,
    file_sha256                 CHAR(64) NOT NULL,
    started_at                  DATETIME NOT NULL,
    finished_at                 DATETIME NOT NULL,
    status                      VARCHAR(32) NOT NULL,
    message                     TEXT NULL,
    INDEX idx_import_release (release_key),
    CONSTRAINT fk_import_release
      FOREIGN KEY (release_key) REFERENCES oddb_release(release_key)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS oddb_validation_result (
    validation_id               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    check_name                  VARCHAR(255) NOT NULL,
    severity                    VARCHAR(16) NOT NULL,
    problem_count               BIGINT UNSIGNED NOT NULL DEFAULT 0,
    details                     TEXT NULL,
    validated_at                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_validation_problem (problem_count)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease (
    disease_id                  VARCHAR(64) PRIMARY KEY,
    disease_name                VARCHAR(512) NOT NULL,
    localization               VARCHAR(255) NULL,
    mondo_id                    VARCHAR(64) NULL,
    omim_id                     VARCHAR(64) NULL,
    orphanet_id                 VARCHAR(64) NULL,
    cui                         VARCHAR(64) NULL,
    inheritance                 VARCHAR(255) NULL,
    curation_status             VARCHAR(128) NULL,
    source                      VARCHAR(255) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    INDEX idx_disease_name (disease_name(191)),
    INDEX idx_disease_mondo (mondo_id),
    INDEX idx_disease_omim (omim_id),
    INDEX idx_disease_orpha (orphanet_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_alias (
    disease_alias_id            VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    alias                       VARCHAR(512) NOT NULL,
    alias_type                  VARCHAR(128) NULL,
    source                      VARCHAR(255) NULL,
    source_id                   VARCHAR(255) NULL,
    curation_status             VARCHAR(128) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    INDEX idx_da_disease (disease_id),
    INDEX idx_da_alias (alias(191)),
    CONSTRAINT fk_da_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS gene (
    hgnc_id                     VARCHAR(32) PRIMARY KEY,
    gene_symbol                 VARCHAR(128) NOT NULL,
    gene_name                   VARCHAR(512) NULL,
    ensembl_gene_id             VARCHAR(64) NULL,
    ncbi_gene_id                VARCHAR(64) NULL,
    chromosome                  VARCHAR(32) NULL,
    chromosome_location         VARCHAR(64) NULL,
    gene_entity_type            VARCHAR(128) NULL,
    hgnc_status                 VARCHAR(128) NULL,
    source                      VARCHAR(255) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_gene_symbol (gene_symbol),
    INDEX idx_gene_ensembl (ensembl_gene_id),
    INDEX idx_gene_ncbi (ncbi_gene_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS locus (
    locus_id                    VARCHAR(96) PRIMARY KEY,
    locus_label                 VARCHAR(255) NOT NULL,
    chromosome_location         VARCHAR(128) NULL,
    related_genes               TEXT NULL,
    locus_type                  VARCHAR(128) NULL,
    source                      VARCHAR(255) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    INDEX idx_locus_label (locus_label(191))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS variant (
    variant_id                  VARCHAR(96) PRIMARY KEY,
    clinvar_variation_id        VARCHAR(64) NULL,
    variant_name                TEXT NULL,
    variant_type                VARCHAR(128) NULL,
    clinical_significance       VARCHAR(255) NULL,
    review_status               VARCHAR(255) NULL,
    chromosome                  VARCHAR(32) NULL,
    position_start              BIGINT NULL,
    position_stop               BIGINT NULL,
    reference_allele            TEXT NULL,
    alternate_allele            TEXT NULL,
    hgvs                        TEXT NULL,
    rs_id                       VARCHAR(64) NULL,
    assembly                    VARCHAR(64) NULL,
    source                      VARCHAR(255) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_variant_clinvar (clinvar_variation_id),
    INDEX idx_variant_rs (rs_id),
    INDEX idx_variant_chr_pos (chromosome, position_start)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS drug (
    drug_id                     VARCHAR(64) PRIMARY KEY,
    preferred_name              VARCHAR(512) NOT NULL,
    normalized_name             VARCHAR(512) NULL,
    standard_inchikey           VARCHAR(64) NULL,
    pubchem_cid                 VARCHAR(64) NULL,
    drugbank_id                 VARCHAR(64) NULL,
    chembl_id                   VARCHAR(64) NULL,
    chembl_id_alternative       TEXT NULL,
    unii                        VARCHAR(64) NULL,
    drugbank_salt_id            VARCHAR(64) NULL,
    parent_drugbank_id          VARCHAR(64) NULL,
    drug_entity_type            VARCHAR(128) NULL,
    identity_basis              VARCHAR(255) NULL,
    identifier_curation_status  VARCHAR(255) NULL,
    opentargets_drug_ids        TEXT NULL,
    opentargets_name            VARCHAR(512) NULL,
    opentargets_drug_type       VARCHAR(128) NULL,
    opentargets_parent_id       VARCHAR(64) NULL,
    maximum_clinical_stage      VARCHAR(128) NULL,
    identity_refinement_status  VARCHAR(128) NULL,
    identity_refinement_notes   TEXT NULL,
    source                      VARCHAR(255) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    INDEX idx_drug_name (preferred_name(191)),
    INDEX idx_drug_chembl (chembl_id),
    INDEX idx_drug_drugbank (drugbank_id),
    INDEX idx_drug_pubchem (pubchem_cid),
    INDEX idx_drug_inchikey (standard_inchikey)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS clinical_report (
    clinical_report_id          VARCHAR(64) PRIMARY KEY,
    opentargets_clinical_report_id VARCHAR(255) NULL,
    report_type                 VARCHAR(128) NULL,
    clinical_stage              VARCHAR(128) NULL,
    origin                      VARCHAR(128) NULL,
    source                      VARCHAR(255) NULL,
    provider                    VARCHAR(255) NULL,
    title                       TEXT NULL,
    trial_official_title        TEXT NULL,
    nct_ids                     TEXT NULL,
    trial_phase                 VARCHAR(128) NULL,
    trial_overall_status        VARCHAR(128) NULL,
    url                         TEXT NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    INDEX idx_cr_otid (opentargets_clinical_report_id(191)),
    INDEX idx_cr_source (source),
    INDEX idx_cr_origin (origin)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS clinical_trial (
    clinical_trial_id           VARCHAR(32) PRIMARY KEY,
    nct_id                      VARCHAR(32) NOT NULL,
    clinical_report_id          VARCHAR(64) NOT NULL,
    title                       TEXT NULL,
    official_title              TEXT NULL,
    phase                       VARCHAR(128) NULL,
    overall_status              VARCHAR(128) NULL,
    study_type                  VARCHAR(128) NULL,
    start_date                  VARCHAR(64) NULL,
    completion_date             VARCHAR(64) NULL,
    source                      VARCHAR(255) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_trial_nct (nct_id),
    INDEX idx_trial_report (clinical_report_id),
    CONSTRAINT fk_trial_report
      FOREIGN KEY (clinical_report_id) REFERENCES clinical_report(clinical_report_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_gene_association (
    association_id              VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    hgnc_id                     VARCHAR(32) NOT NULL,
    gene_symbol                 VARCHAR(128) NULL,
    inheritance                 VARCHAR(255) NULL,
    evidence_class              VARCHAR(128) NULL,
    evidence_status             VARCHAR(128) NULL,
    source                      VARCHAR(255) NULL,
    source_id                   VARCHAR(255) NULL,
    pmid                        TEXT NULL,
    doi                         TEXT NULL,
    curation_status             VARCHAR(128) NULL,
    curator_notes               TEXT NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_dga_natural (disease_id, hgnc_id, inheritance(128)),
    INDEX idx_dga_gene (hgnc_id),
    CONSTRAINT fk_dga_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dga_gene
      FOREIGN KEY (hgnc_id) REFERENCES gene(hgnc_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_gene_association_reclassified (
    reclassified_id             VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    original_hgnc_id            VARCHAR(32) NULL,
    original_gene_symbol        VARCHAR(128) NULL,
    reclassification_type       VARCHAR(128) NULL,
    rationale                   TEXT NULL,
    source                      VARCHAR(255) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    INDEX idx_dgar_disease (disease_id),
    CONSTRAINT fk_dgar_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_locus_association (
    association_id              VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    locus_id                    VARCHAR(96) NOT NULL,
    evidence_class              VARCHAR(128) NULL,
    evidence_status             VARCHAR(128) NULL,
    source                      VARCHAR(255) NULL,
    source_id                   VARCHAR(255) NULL,
    pmid                        TEXT NULL,
    doi                         TEXT NULL,
    curation_status             VARCHAR(128) NULL,
    curator_notes               TEXT NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_dla_natural (disease_id, locus_id),
    INDEX idx_dla_locus (locus_id),
    CONSTRAINT fk_dla_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dla_locus
      FOREIGN KEY (locus_id) REFERENCES locus(locus_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS gene_variant_association (
    association_id              VARCHAR(96) PRIMARY KEY,
    hgnc_id                     VARCHAR(32) NOT NULL,
    variant_id                  VARCHAR(96) NOT NULL,
    gene_symbol                 VARCHAR(128) NULL,
    relationship_type           VARCHAR(128) NULL,
    source                      VARCHAR(255) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_gva_natural (hgnc_id, variant_id),
    INDEX idx_gva_variant (variant_id),
    CONSTRAINT fk_gva_gene
      FOREIGN KEY (hgnc_id) REFERENCES gene(hgnc_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_gva_variant
      FOREIGN KEY (variant_id) REFERENCES variant(variant_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_variant_association (
    association_id              VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    variant_id                  VARCHAR(96) NOT NULL,
    mapping_method              VARCHAR(255) NULL,
    evidence_class              VARCHAR(128) NULL,
    source                      VARCHAR(255) NULL,
    source_id                   VARCHAR(255) NULL,
    curation_status             VARCHAR(128) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_dva_natural (disease_id, variant_id),
    INDEX idx_dva_variant (variant_id),
    CONSTRAINT fk_dva_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dva_variant
      FOREIGN KEY (variant_id) REFERENCES variant(variant_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS drug_target_association (
    drug_target_association_id  VARCHAR(96) PRIMARY KEY,
    drug_id                     VARCHAR(64) NOT NULL,
    hgnc_id                     VARCHAR(32) NOT NULL,
    gene_symbol                 VARCHAR(128) NULL,
    ensembl_gene_id             VARCHAR(64) NULL,
    mechanism_of_action         TEXT NULL,
    action_type                 VARCHAR(128) NULL,
    target_name                 VARCHAR(512) NULL,
    target_type                 VARCHAR(128) NULL,
    source                      VARCHAR(255) NULL,
    source_id                   VARCHAR(255) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    INDEX idx_dta_drug (drug_id),
    INDEX idx_dta_gene (hgnc_id),
    INDEX idx_dta_action (action_type),
    CONSTRAINT fk_dta_drug
      FOREIGN KEY (drug_id) REFERENCES drug(drug_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dta_gene
      FOREIGN KEY (hgnc_id) REFERENCES gene(hgnc_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS drug_form_relationship (
    drug_form_relationship_id   VARCHAR(96) PRIMARY KEY,
    child_drug_id               VARCHAR(64) NOT NULL,
    parent_drug_id              VARCHAR(64) NOT NULL,
    relationship_type           VARCHAR(128) NOT NULL,
    child_chembl_id             VARCHAR(64) NULL,
    parent_chembl_id            VARCHAR(64) NULL,
    evidence_basis              TEXT NULL,
    source                      VARCHAR(255) NULL,
    source_id                   VARCHAR(255) NULL,
    curation_status             VARCHAR(128) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_dfr_natural (child_drug_id, parent_drug_id),
    INDEX idx_dfr_parent (parent_drug_id),
    CONSTRAINT fk_dfr_child
      FOREIGN KEY (child_drug_id) REFERENCES drug(drug_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dfr_parent
      FOREIGN KEY (parent_drug_id) REFERENCES drug(drug_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_clinical_report_association (
    association_id              VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    clinical_report_id          VARCHAR(64) NOT NULL,
    source_disease_id           VARCHAR(255) NULL,
    source_disease_name         VARCHAR(512) NULL,
    match_method                VARCHAR(255) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_dcr_natural (disease_id, clinical_report_id),
    INDEX idx_dcr_report (clinical_report_id),
    CONSTRAINT fk_dcr_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dcr_report
      FOREIGN KEY (clinical_report_id) REFERENCES clinical_report(clinical_report_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS drug_clinical_report_association (
    association_id              VARCHAR(96) PRIMARY KEY,
    drug_id                     VARCHAR(64) NOT NULL,
    clinical_report_id          VARCHAR(64) NOT NULL,
    drug_name                   VARCHAR(512) NULL,
    source_drug_id              VARCHAR(255) NULL,
    source_drug_name            VARCHAR(512) NULL,
    match_method                VARCHAR(255) NULL,
    identity_resolution_status  VARCHAR(128) NULL,
    identity_resolution_notes   TEXT NULL,
    original_drug_id            VARCHAR(64) NULL,
    original_drug_name          VARCHAR(512) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_drcr_natural (drug_id, clinical_report_id),
    INDEX idx_drcr_report (clinical_report_id),
    INDEX idx_drcr_status (identity_resolution_status),
    CONSTRAINT fk_drcr_drug
      FOREIGN KEY (drug_id) REFERENCES drug(drug_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_drcr_report
      FOREIGN KEY (clinical_report_id) REFERENCES clinical_report(clinical_report_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_clinical_trial_association (
    association_id              VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    clinical_trial_id           VARCHAR(32) NOT NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_dct_natural (disease_id, clinical_trial_id),
    INDEX idx_dct_trial (clinical_trial_id),
    CONSTRAINT fk_dct_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dct_trial
      FOREIGN KEY (clinical_trial_id) REFERENCES clinical_trial(clinical_trial_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS drug_clinical_trial_association (
    association_id              VARCHAR(96) PRIMARY KEY,
    drug_id                     VARCHAR(64) NOT NULL,
    clinical_trial_id           VARCHAR(32) NOT NULL,
    drug_name                   VARCHAR(512) NULL,
    identity_resolution_status  VARCHAR(128) NULL,
    identity_resolution_notes   TEXT NULL,
    original_drug_id            VARCHAR(64) NULL,
    original_drug_name          VARCHAR(512) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_drct_natural (drug_id, clinical_trial_id),
    INDEX idx_drct_trial (clinical_trial_id),
    INDEX idx_drct_status (identity_resolution_status),
    CONSTRAINT fk_drct_drug
      FOREIGN KEY (drug_id) REFERENCES drug(drug_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_drct_trial
      FOREIGN KEY (clinical_trial_id) REFERENCES clinical_trial(clinical_trial_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_drug_association (
    disease_drug_association_id VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    drug_id                     VARCHAR(64) NOT NULL,
    disease_name                VARCHAR(512) NULL,
    drug_name                   VARCHAR(512) NULL,
    association_class           VARCHAR(128) NULL,
    evidence_strength_class     VARCHAR(128) NULL,
    has_clinical_trial_evidence TINYINT(1) NULL,
    has_drug_label_evidence     TINYINT(1) NULL,
    has_regulatory_evidence     TINYINT(1) NULL,
    has_curated_indication_evidence TINYINT(1) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_dda_natural (disease_id, drug_id),
    INDEX idx_dda_drug (drug_id),
    CONSTRAINT fk_dda_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dda_drug
      FOREIGN KEY (drug_id) REFERENCES drug(drug_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_drug_evidence (
    disease_drug_evidence_id    VARCHAR(96) PRIMARY KEY,
    disease_drug_association_id VARCHAR(96) NOT NULL,
    disease_id                  VARCHAR(64) NOT NULL,
    drug_id                     VARCHAR(64) NOT NULL,
    evidence_subtype            VARCHAR(128) NULL,
    evidence_strength_class     VARCHAR(128) NULL,
    clinical_report_id          VARCHAR(64) NULL,
    clinical_trial_id           VARCHAR(32) NULL,
    source                      VARCHAR(255) NULL,
    source_id                   VARCHAR(255) NULL,
    clinical_stage              VARCHAR(128) NULL,
    evidence_text               TEXT NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    INDEX idx_dde_dda (disease_drug_association_id),
    INDEX idx_dde_pair (disease_id, drug_id),
    INDEX idx_dde_report (clinical_report_id),
    INDEX idx_dde_trial (clinical_trial_id),
    CONSTRAINT fk_dde_dda
      FOREIGN KEY (disease_drug_association_id)
      REFERENCES disease_drug_association(disease_drug_association_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dde_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dde_drug
      FOREIGN KEY (drug_id) REFERENCES drug(drug_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dde_report
      FOREIGN KEY (clinical_report_id) REFERENCES clinical_report(clinical_report_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dde_trial
      FOREIGN KEY (clinical_trial_id) REFERENCES clinical_trial(clinical_trial_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_drug_aggregate_context (
    aggregate_context_id        VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    drug_id                     VARCHAR(64) NOT NULL,
    aggregate_context_class     VARCHAR(255) NULL,
    source                      VARCHAR(255) NULL,
    source_id                   VARCHAR(255) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    INDEX idx_ddac_pair (disease_id, drug_id),
    CONSTRAINT fk_ddac_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_ddac_drug
      FOREIGN KEY (drug_id) REFERENCES drug(drug_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_drug_aggregate_context_demoted (
    aggregate_context_id        VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    drug_id                     VARCHAR(64) NOT NULL,
    aggregate_context_class     VARCHAR(255) NULL,
    source                      VARCHAR(255) NULL,
    source_id                   VARCHAR(255) NULL,
    demotion_reason             TEXT NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    INDEX idx_ddacd_pair (disease_id, drug_id),
    CONSTRAINT fk_ddacd_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_ddacd_drug
      FOREIGN KEY (drug_id) REFERENCES drug(drug_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_drug_target_overlap (
    disease_drug_target_overlap_id VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    drug_id                     VARCHAR(64) NOT NULL,
    hgnc_id                     VARCHAR(32) NOT NULL,
    gene_symbol                 VARCHAR(128) NULL,
    direct_disease_drug_evidence TINYINT(1) NOT NULL DEFAULT 0,
    action_type                 VARCHAR(128) NULL,
    mechanism_of_action         TEXT NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    INDEX idx_ddto_pair (disease_id, drug_id),
    INDEX idx_ddto_gene (hgnc_id),
    CONSTRAINT fk_ddto_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_ddto_drug
      FOREIGN KEY (drug_id) REFERENCES drug(drug_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_ddto_gene
      FOREIGN KEY (hgnc_id) REFERENCES gene(hgnc_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_drug_target_overlap_summary (
    summary_id                  VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    drug_id                     VARCHAR(64) NOT NULL,
    direct_disease_drug_evidence TINYINT(1) NOT NULL DEFAULT 0,
    target_gene_count           INT NULL,
    target_genes                TEXT NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_ddtos_pair (disease_id, drug_id),
    INDEX idx_ddtos_drug (drug_id),
    CONSTRAINT fk_ddtos_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_ddtos_drug
      FOREIGN KEY (drug_id) REFERENCES drug(drug_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_drug_direct_without_target_overlap (
    record_id                   VARCHAR(96) PRIMARY KEY,
    disease_id                  VARCHAR(64) NOT NULL,
    drug_id                     VARCHAR(64) NOT NULL,
    disease_drug_association_id VARCHAR(96) NULL,
    source_release              VARCHAR(128) NULL,
    source_file                 VARCHAR(255) NOT NULL,
    source_record_json          LONGTEXT NOT NULL,
    UNIQUE KEY uq_dddwto_pair (disease_id, drug_id),
    CONSTRAINT fk_dddwto_disease
      FOREIGN KEY (disease_id) REFERENCES disease(disease_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dddwto_drug
      FOREIGN KEY (drug_id) REFERENCES drug(drug_id)
      ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_dddwto_dda
      FOREIGN KEY (disease_drug_association_id)
      REFERENCES disease_drug_association(disease_drug_association_id)
      ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- -------------------------
-- Views for application use
-- -------------------------

CREATE OR REPLACE VIEW vw_direct_therapeutic_evidence AS
SELECT
    dda.disease_drug_association_id,
    dda.disease_id,
    d.disease_name,
    dda.drug_id,
    dr.preferred_name AS drug_name,
    dda.evidence_strength_class,
    dde.disease_drug_evidence_id,
    dde.evidence_subtype,
    dde.clinical_report_id,
    dde.clinical_trial_id,
    dde.source,
    dde.source_id,
    dde.clinical_stage
FROM disease_drug_association dda
JOIN disease d ON d.disease_id = dda.disease_id
JOIN drug dr ON dr.drug_id = dda.drug_id
LEFT JOIN disease_drug_evidence dde
  ON dde.disease_drug_association_id = dda.disease_drug_association_id;

CREATE OR REPLACE VIEW vw_target_overlap_discovery AS
SELECT
    s.disease_id,
    d.disease_name,
    s.drug_id,
    dr.preferred_name AS drug_name,
    s.direct_disease_drug_evidence,
    s.target_gene_count,
    s.target_genes,
    CASE
      WHEN s.direct_disease_drug_evidence = 1
        THEN 'target_overlap_plus_direct_evidence'
      ELSE 'target_overlap_only_discovery'
    END AS display_class
FROM disease_drug_target_overlap_summary s
JOIN disease d ON d.disease_id = s.disease_id
JOIN drug dr ON dr.drug_id = s.drug_id;

CREATE OR REPLACE VIEW vw_drug_forms AS
SELECT
    r.drug_form_relationship_id,
    r.child_drug_id,
    c.preferred_name AS child_drug_name,
    r.relationship_type,
    r.parent_drug_id,
    p.preferred_name AS parent_drug_name,
    r.child_chembl_id,
    r.parent_chembl_id,
    r.evidence_basis,
    r.curation_status
FROM drug_form_relationship r
JOIN drug c ON c.drug_id = r.child_drug_id
JOIN drug p ON p.drug_id = r.parent_drug_id;

CREATE OR REPLACE VIEW vw_clinical_trial_disease_drug AS
SELECT
    ct.clinical_trial_id,
    ct.nct_id,
    ct.title,
    ct.phase,
    ct.overall_status,
    dct.disease_id,
    d.disease_name,
    drct.drug_id,
    dr.preferred_name AS drug_name,
    drct.identity_resolution_status
FROM clinical_trial ct
JOIN disease_clinical_trial_association dct
  ON dct.clinical_trial_id = ct.clinical_trial_id
JOIN drug_clinical_trial_association drct
  ON drct.clinical_trial_id = ct.clinical_trial_id
JOIN disease d ON d.disease_id = dct.disease_id
JOIN drug dr ON dr.drug_id = drct.drug_id;
