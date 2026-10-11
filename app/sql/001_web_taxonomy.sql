USE oddb_v1;

CREATE TABLE IF NOT EXISTS disease_category (
    category_id VARCHAR(32) PRIMARY KEY,
    category_system VARCHAR(32) NOT NULL,
    category_name VARCHAR(128) NOT NULL,
    display_order INT NOT NULL,
    UNIQUE KEY uq_disease_category (category_system, category_name),
    INDEX idx_dc_system_order (category_system, display_order)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS disease_category_membership (
    disease_id VARCHAR(64) NOT NULL,
    category_id VARCHAR(32) NOT NULL,
    membership_basis VARCHAR(255) NULL,
    source VARCHAR(128) NOT NULL DEFAULT 'ODDB v1',
    curation_status VARCHAR(64) NOT NULL DEFAULT 'mapped',
    PRIMARY KEY (disease_id, category_id),
    INDEX idx_dcm_category (category_id, disease_id),
    CONSTRAINT fk_dcm_disease FOREIGN KEY (disease_id)
      REFERENCES disease(disease_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_dcm_category FOREIGN KEY (category_id)
      REFERENCES disease_category(category_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS gene_category (
    gene_category_id VARCHAR(32) PRIMARY KEY,
    category_name VARCHAR(128) NOT NULL UNIQUE,
    entity_scope VARCHAR(32) NOT NULL DEFAULT 'gene',
    display_order INT NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS gene_category_membership (
    hgnc_id VARCHAR(32) NOT NULL,
    gene_category_id VARCHAR(32) NOT NULL,
    membership_basis VARCHAR(255) NULL,
    source VARCHAR(128) NOT NULL DEFAULT 'ODDB v1',
    PRIMARY KEY (hgnc_id, gene_category_id),
    INDEX idx_gcm_category (gene_category_id, hgnc_id),
    CONSTRAINT fk_gcm_gene FOREIGN KEY (hgnc_id)
      REFERENCES gene(hgnc_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_gcm_category FOREIGN KEY (gene_category_id)
      REFERENCES gene_category(gene_category_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS variant_consequence_category (
    consequence_id VARCHAR(32) PRIMARY KEY,
    consequence_term VARCHAR(128) NOT NULL UNIQUE,
    display_order INT NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS variant_consequence (
    variant_consequence_id VARCHAR(96) PRIMARY KEY,
    variant_id VARCHAR(96) NOT NULL,
    consequence_id VARCHAR(32) NOT NULL,
    hgnc_id VARCHAR(32) NULL,
    transcript_id VARCHAR(64) NULL,
    source VARCHAR(128) NOT NULL DEFAULT 'ODDB source field',
    source_value VARCHAR(255) NULL,
    UNIQUE KEY uq_variant_consequence_gene (variant_id, consequence_id, hgnc_id),
    INDEX idx_vc_consequence (consequence_id, variant_id),
    INDEX idx_vc_gene (hgnc_id),
    CONSTRAINT fk_vc_variant FOREIGN KEY (variant_id)
      REFERENCES variant(variant_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_vc_category FOREIGN KEY (consequence_id)
      REFERENCES variant_consequence_category(consequence_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_vc_gene FOREIGN KEY (hgnc_id)
      REFERENCES gene(hgnc_id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS entity_external_link (
    link_id VARCHAR(96) PRIMARY KEY,
    entity_type VARCHAR(32) NOT NULL,
    entity_id VARCHAR(96) NOT NULL,
    resource_name VARCHAR(128) NOT NULL,
    external_id VARCHAR(255) NULL,
    url TEXT NOT NULL,
    display_label VARCHAR(255) NULL,
    display_order INT NOT NULL DEFAULT 100,
    source VARCHAR(128) NOT NULL DEFAULT 'generated_from_canonical_identifier',
    UNIQUE KEY uq_entity_resource_url (entity_type, entity_id, resource_name, url(255)),
    INDEX idx_external_entity (entity_type, entity_id),
    INDEX idx_external_resource (resource_name)
) ENGINE=InnoDB;

INSERT INTO disease_category
(category_id, category_system, category_name, display_order) VALUES
('ANAT-01','anatomy','Refractive Errors',1),
('ANAT-02','anatomy','Retinal Diseases',2),
('ANAT-03','anatomy','Others',3),
('ANAT-04','anatomy','Lens Diseases',4),
('ANAT-05','anatomy','Ocular Hypertension',5),
('ANAT-06','anatomy','Ocular Motility Disorders',6),
('ANAT-07','anatomy','Uveal Diseases',7),
('ANAT-08','anatomy','Corneal Diseases',8),
('ANAT-09','anatomy','Conjunctival Diseases',9),
('ANAT-10','anatomy','Orbital Diseases',10),
('ANAT-11','anatomy','Eye Neoplasms',11),
('ANAT-12','anatomy','Lacrimal Apparatus Diseases',12),
('INH-01','inheritance','Autosomal dominant',1),
('INH-02','inheritance','Autosomal recessive',2),
('INH-03','inheritance','Isolated cases',3),
('INH-04','inheritance','Mitochondrial',4),
('INH-05','inheritance','Other',5),
('INH-06','inheritance','X-linked dominant',6),
('INH-07','inheritance','X-linked recessive',7)
ON DUPLICATE KEY UPDATE category_name=VALUES(category_name),display_order=VALUES(display_order);

INSERT INTO gene_category
(gene_category_id, category_name, entity_scope, display_order) VALUES
('GENE-01','Pseudogene','gene',1),
('GENE-02','Genetic Locus','locus',2),
('GENE-03','lncRNA','gene',3),
('GENE-04','miRNA','gene',4),
('GENE-05','mt_tRNA','gene',5),
('GENE-06','Other','gene',6),
('GENE-07','Protein coding','gene',7),
('GENE-08','RNA gene','gene',8)
ON DUPLICATE KEY UPDATE category_name=VALUES(category_name),entity_scope=VALUES(entity_scope),display_order=VALUES(display_order);

INSERT INTO variant_consequence_category
(consequence_id, consequence_term, display_order) VALUES
('VARC-01','missense variant',1),
('VARC-02','inframe deletion',2),
('VARC-03','frameshift variant',3),
('VARC-04','intron variant',4),
('VARC-05','regulatory region variant',5),
('VARC-06','intergenic variant',6),
('VARC-07','splice region variant',7),
('VARC-08','splice donor variant',8),
('VARC-09','non coding transcript exon variant',9),
('VARC-10','3-prime UTR variant',10),
('VARC-11','5-prime UTR variant',11),
('VARC-12','stop gained',12),
('VARC-13','synonymous variant',13),
('VARC-14','TF binding site variant',14),
('VARC-15','splice acceptor variant',15),
('VARC-16','downstream gene variant',16),
('VARC-17','stop lost',17),
('VARC-18','upstream gene variant',18),
('VARC-19','inframe insertion',19),
('VARC-20','protein altering variant',20),
('VARC-21','Multiple reported',21)
ON DUPLICATE KEY UPDATE consequence_term=VALUES(consequence_term),display_order=VALUES(display_order);
