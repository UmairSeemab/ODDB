-- MariaDB dump 10.19  Distrib 10.4.28-MariaDB, for Linux (x86_64)
--
-- Host: 127.0.0.1    Database: oddb_v1
-- ------------------------------------------------------
-- Server version	10.4.28-MariaDB

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `clinical_report`
--

DROP TABLE IF EXISTS `clinical_report`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `clinical_report` (
  `clinical_report_id` varchar(64) NOT NULL,
  `opentargets_clinical_report_id` varchar(255) DEFAULT NULL,
  `report_type` varchar(128) DEFAULT NULL,
  `clinical_stage` varchar(128) DEFAULT NULL,
  `origin` varchar(128) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `provider` varchar(255) DEFAULT NULL,
  `title` text DEFAULT NULL,
  `trial_official_title` text DEFAULT NULL,
  `nct_ids` text DEFAULT NULL,
  `trial_phase` varchar(128) DEFAULT NULL,
  `trial_overall_status` varchar(128) DEFAULT NULL,
  `url` text DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`clinical_report_id`),
  KEY `idx_cr_otid` (`opentargets_clinical_report_id`(191)),
  KEY `idx_cr_source` (`source`),
  KEY `idx_cr_origin` (`origin`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `clinical_trial`
--

DROP TABLE IF EXISTS `clinical_trial`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `clinical_trial` (
  `clinical_trial_id` varchar(32) NOT NULL,
  `nct_id` varchar(32) NOT NULL,
  `clinical_report_id` varchar(64) NOT NULL,
  `title` text DEFAULT NULL,
  `official_title` text DEFAULT NULL,
  `phase` varchar(128) DEFAULT NULL,
  `overall_status` varchar(128) DEFAULT NULL,
  `study_type` varchar(128) DEFAULT NULL,
  `start_date` varchar(64) DEFAULT NULL,
  `completion_date` varchar(64) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`clinical_trial_id`),
  UNIQUE KEY `uq_trial_nct` (`nct_id`),
  KEY `idx_trial_report` (`clinical_report_id`),
  CONSTRAINT `fk_trial_report` FOREIGN KEY (`clinical_report_id`) REFERENCES `clinical_report` (`clinical_report_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease`
--

DROP TABLE IF EXISTS `disease`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease` (
  `disease_id` varchar(64) NOT NULL,
  `disease_name` varchar(512) NOT NULL,
  `localization` varchar(255) DEFAULT NULL,
  `mondo_id` varchar(64) DEFAULT NULL,
  `omim_id` varchar(64) DEFAULT NULL,
  `orphanet_id` varchar(64) DEFAULT NULL,
  `cui` varchar(64) DEFAULT NULL,
  `inheritance` varchar(255) DEFAULT NULL,
  `curation_status` varchar(128) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`disease_id`),
  KEY `idx_disease_name` (`disease_name`(191)),
  KEY `idx_disease_mondo` (`mondo_id`),
  KEY `idx_disease_omim` (`omim_id`),
  KEY `idx_disease_orpha` (`orphanet_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_alias`
--

DROP TABLE IF EXISTS `disease_alias`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_alias` (
  `disease_alias_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `alias` varchar(512) NOT NULL,
  `alias_type` varchar(128) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_id` varchar(255) DEFAULT NULL,
  `curation_status` varchar(128) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`disease_alias_id`),
  KEY `idx_da_disease` (`disease_id`),
  KEY `idx_da_alias` (`alias`(191)),
  CONSTRAINT `fk_da_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_category`
--

DROP TABLE IF EXISTS `disease_category`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_category` (
  `category_id` varchar(32) NOT NULL,
  `category_system` varchar(32) NOT NULL,
  `category_name` varchar(128) NOT NULL,
  `display_order` int(11) NOT NULL,
  PRIMARY KEY (`category_id`),
  UNIQUE KEY `uq_disease_category` (`category_system`,`category_name`),
  KEY `idx_dc_system_order` (`category_system`,`display_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_category_membership`
--

DROP TABLE IF EXISTS `disease_category_membership`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_category_membership` (
  `disease_id` varchar(64) NOT NULL,
  `category_id` varchar(32) NOT NULL,
  `membership_basis` varchar(255) DEFAULT NULL,
  `source` varchar(128) NOT NULL DEFAULT 'ODDB v1',
  `curation_status` varchar(64) NOT NULL DEFAULT 'mapped',
  PRIMARY KEY (`disease_id`,`category_id`),
  KEY `idx_dcm_category` (`category_id`,`disease_id`),
  CONSTRAINT `fk_dcm_category` FOREIGN KEY (`category_id`) REFERENCES `disease_category` (`category_id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_dcm_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_clinical_report_association`
--

DROP TABLE IF EXISTS `disease_clinical_report_association`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_clinical_report_association` (
  `association_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `clinical_report_id` varchar(64) NOT NULL,
  `source_disease_id` varchar(255) DEFAULT NULL,
  `source_disease_name` varchar(512) DEFAULT NULL,
  `match_method` varchar(255) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`association_id`),
  UNIQUE KEY `uq_dcr_natural` (`disease_id`,`clinical_report_id`),
  KEY `idx_dcr_report` (`clinical_report_id`),
  CONSTRAINT `fk_dcr_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dcr_report` FOREIGN KEY (`clinical_report_id`) REFERENCES `clinical_report` (`clinical_report_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_clinical_trial_association`
--

DROP TABLE IF EXISTS `disease_clinical_trial_association`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_clinical_trial_association` (
  `association_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `clinical_trial_id` varchar(32) NOT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`association_id`),
  UNIQUE KEY `uq_dct_natural` (`disease_id`,`clinical_trial_id`),
  KEY `idx_dct_trial` (`clinical_trial_id`),
  CONSTRAINT `fk_dct_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dct_trial` FOREIGN KEY (`clinical_trial_id`) REFERENCES `clinical_trial` (`clinical_trial_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_drug_aggregate_context`
--

DROP TABLE IF EXISTS `disease_drug_aggregate_context`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_drug_aggregate_context` (
  `aggregate_context_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `drug_id` varchar(64) NOT NULL,
  `aggregate_context_class` varchar(255) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_id` varchar(255) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`aggregate_context_id`),
  KEY `idx_ddac_pair` (`disease_id`,`drug_id`),
  KEY `fk_ddac_drug` (`drug_id`),
  CONSTRAINT `fk_ddac_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_ddac_drug` FOREIGN KEY (`drug_id`) REFERENCES `drug` (`drug_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_drug_aggregate_context_demoted`
--

DROP TABLE IF EXISTS `disease_drug_aggregate_context_demoted`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_drug_aggregate_context_demoted` (
  `aggregate_context_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `drug_id` varchar(64) NOT NULL,
  `aggregate_context_class` varchar(255) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_id` varchar(255) DEFAULT NULL,
  `demotion_reason` text DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`aggregate_context_id`),
  KEY `idx_ddacd_pair` (`disease_id`,`drug_id`),
  KEY `fk_ddacd_drug` (`drug_id`),
  CONSTRAINT `fk_ddacd_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_ddacd_drug` FOREIGN KEY (`drug_id`) REFERENCES `drug` (`drug_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_drug_association`
--

DROP TABLE IF EXISTS `disease_drug_association`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_drug_association` (
  `disease_drug_association_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `drug_id` varchar(64) NOT NULL,
  `disease_name` varchar(512) DEFAULT NULL,
  `drug_name` varchar(512) DEFAULT NULL,
  `association_class` varchar(128) DEFAULT NULL,
  `evidence_strength_class` varchar(128) DEFAULT NULL,
  `has_clinical_trial_evidence` tinyint(1) DEFAULT NULL,
  `has_drug_label_evidence` tinyint(1) DEFAULT NULL,
  `has_regulatory_evidence` tinyint(1) DEFAULT NULL,
  `has_curated_indication_evidence` tinyint(1) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`disease_drug_association_id`),
  UNIQUE KEY `uq_dda_natural` (`disease_id`,`drug_id`),
  KEY `idx_dda_drug` (`drug_id`),
  CONSTRAINT `fk_dda_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dda_drug` FOREIGN KEY (`drug_id`) REFERENCES `drug` (`drug_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_drug_direct_without_target_overlap`
--

DROP TABLE IF EXISTS `disease_drug_direct_without_target_overlap`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_drug_direct_without_target_overlap` (
  `record_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `drug_id` varchar(64) NOT NULL,
  `disease_drug_association_id` varchar(96) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`record_id`),
  UNIQUE KEY `uq_dddwto_pair` (`disease_id`,`drug_id`),
  KEY `fk_dddwto_drug` (`drug_id`),
  KEY `fk_dddwto_dda` (`disease_drug_association_id`),
  CONSTRAINT `fk_dddwto_dda` FOREIGN KEY (`disease_drug_association_id`) REFERENCES `disease_drug_association` (`disease_drug_association_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dddwto_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dddwto_drug` FOREIGN KEY (`drug_id`) REFERENCES `drug` (`drug_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_drug_evidence`
--

DROP TABLE IF EXISTS `disease_drug_evidence`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_drug_evidence` (
  `disease_drug_evidence_id` varchar(96) NOT NULL,
  `disease_drug_association_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `drug_id` varchar(64) NOT NULL,
  `evidence_subtype` varchar(128) DEFAULT NULL,
  `evidence_strength_class` varchar(128) DEFAULT NULL,
  `clinical_report_id` varchar(64) DEFAULT NULL,
  `clinical_trial_id` varchar(32) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_id` varchar(255) DEFAULT NULL,
  `clinical_stage` varchar(128) DEFAULT NULL,
  `evidence_text` text DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`disease_drug_evidence_id`),
  KEY `idx_dde_dda` (`disease_drug_association_id`),
  KEY `idx_dde_pair` (`disease_id`,`drug_id`),
  KEY `idx_dde_report` (`clinical_report_id`),
  KEY `idx_dde_trial` (`clinical_trial_id`),
  KEY `fk_dde_drug` (`drug_id`),
  CONSTRAINT `fk_dde_dda` FOREIGN KEY (`disease_drug_association_id`) REFERENCES `disease_drug_association` (`disease_drug_association_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dde_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dde_drug` FOREIGN KEY (`drug_id`) REFERENCES `drug` (`drug_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dde_report` FOREIGN KEY (`clinical_report_id`) REFERENCES `clinical_report` (`clinical_report_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dde_trial` FOREIGN KEY (`clinical_trial_id`) REFERENCES `clinical_trial` (`clinical_trial_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_drug_target_overlap`
--

DROP TABLE IF EXISTS `disease_drug_target_overlap`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_drug_target_overlap` (
  `disease_drug_target_overlap_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `drug_id` varchar(64) NOT NULL,
  `hgnc_id` varchar(32) NOT NULL,
  `gene_symbol` varchar(128) DEFAULT NULL,
  `direct_disease_drug_evidence` tinyint(1) NOT NULL DEFAULT 0,
  `action_type` varchar(128) DEFAULT NULL,
  `mechanism_of_action` text DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`disease_drug_target_overlap_id`),
  KEY `idx_ddto_pair` (`disease_id`,`drug_id`),
  KEY `idx_ddto_gene` (`hgnc_id`),
  KEY `fk_ddto_drug` (`drug_id`),
  CONSTRAINT `fk_ddto_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_ddto_drug` FOREIGN KEY (`drug_id`) REFERENCES `drug` (`drug_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_ddto_gene` FOREIGN KEY (`hgnc_id`) REFERENCES `gene` (`hgnc_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_drug_target_overlap_summary`
--

DROP TABLE IF EXISTS `disease_drug_target_overlap_summary`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_drug_target_overlap_summary` (
  `summary_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `drug_id` varchar(64) NOT NULL,
  `direct_disease_drug_evidence` tinyint(1) NOT NULL DEFAULT 0,
  `target_gene_count` int(11) DEFAULT NULL,
  `target_genes` text DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`summary_id`),
  UNIQUE KEY `uq_ddtos_pair` (`disease_id`,`drug_id`),
  KEY `idx_ddtos_drug` (`drug_id`),
  CONSTRAINT `fk_ddtos_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_ddtos_drug` FOREIGN KEY (`drug_id`) REFERENCES `drug` (`drug_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_gene_association`
--

DROP TABLE IF EXISTS `disease_gene_association`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_gene_association` (
  `association_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `hgnc_id` varchar(32) NOT NULL,
  `gene_symbol` varchar(128) DEFAULT NULL,
  `inheritance` varchar(255) DEFAULT NULL,
  `evidence_class` varchar(128) DEFAULT NULL,
  `evidence_status` varchar(128) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_id` varchar(255) DEFAULT NULL,
  `pmid` text DEFAULT NULL,
  `doi` text DEFAULT NULL,
  `curation_status` varchar(128) DEFAULT NULL,
  `curator_notes` text DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`association_id`),
  UNIQUE KEY `uq_dga_natural` (`disease_id`,`hgnc_id`,`inheritance`(128)),
  KEY `idx_dga_gene` (`hgnc_id`),
  CONSTRAINT `fk_dga_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dga_gene` FOREIGN KEY (`hgnc_id`) REFERENCES `gene` (`hgnc_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_gene_association_reclassified`
--

DROP TABLE IF EXISTS `disease_gene_association_reclassified`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_gene_association_reclassified` (
  `reclassified_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `original_hgnc_id` varchar(32) DEFAULT NULL,
  `original_gene_symbol` varchar(128) DEFAULT NULL,
  `reclassification_type` varchar(128) DEFAULT NULL,
  `rationale` text DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`reclassified_id`),
  KEY `idx_dgar_disease` (`disease_id`),
  CONSTRAINT `fk_dgar_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_locus_association`
--

DROP TABLE IF EXISTS `disease_locus_association`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_locus_association` (
  `association_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `locus_id` varchar(96) NOT NULL,
  `evidence_class` varchar(128) DEFAULT NULL,
  `evidence_status` varchar(128) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_id` varchar(255) DEFAULT NULL,
  `pmid` text DEFAULT NULL,
  `doi` text DEFAULT NULL,
  `curation_status` varchar(128) DEFAULT NULL,
  `curator_notes` text DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`association_id`),
  UNIQUE KEY `uq_dla_natural` (`disease_id`,`locus_id`),
  KEY `idx_dla_locus` (`locus_id`),
  CONSTRAINT `fk_dla_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dla_locus` FOREIGN KEY (`locus_id`) REFERENCES `locus` (`locus_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `disease_variant_association`
--

DROP TABLE IF EXISTS `disease_variant_association`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `disease_variant_association` (
  `association_id` varchar(96) NOT NULL,
  `disease_id` varchar(64) NOT NULL,
  `variant_id` varchar(96) NOT NULL,
  `mapping_method` varchar(255) DEFAULT NULL,
  `evidence_class` varchar(128) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_id` varchar(255) DEFAULT NULL,
  `curation_status` varchar(128) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`association_id`),
  UNIQUE KEY `uq_dva_natural` (`disease_id`,`variant_id`),
  KEY `idx_dva_variant` (`variant_id`),
  CONSTRAINT `fk_dva_disease` FOREIGN KEY (`disease_id`) REFERENCES `disease` (`disease_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dva_variant` FOREIGN KEY (`variant_id`) REFERENCES `variant` (`variant_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `drug`
--

DROP TABLE IF EXISTS `drug`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `drug` (
  `drug_id` varchar(64) NOT NULL,
  `preferred_name` varchar(512) NOT NULL,
  `normalized_name` varchar(512) DEFAULT NULL,
  `standard_inchikey` varchar(64) DEFAULT NULL,
  `pubchem_cid` varchar(64) DEFAULT NULL,
  `drugbank_id` varchar(64) DEFAULT NULL,
  `chembl_id` varchar(64) DEFAULT NULL,
  `chembl_id_alternative` text DEFAULT NULL,
  `unii` varchar(64) DEFAULT NULL,
  `drugbank_salt_id` varchar(64) DEFAULT NULL,
  `parent_drugbank_id` varchar(64) DEFAULT NULL,
  `drug_entity_type` varchar(128) DEFAULT NULL,
  `identity_basis` varchar(255) DEFAULT NULL,
  `identifier_curation_status` varchar(255) DEFAULT NULL,
  `opentargets_drug_ids` text DEFAULT NULL,
  `opentargets_name` varchar(512) DEFAULT NULL,
  `opentargets_drug_type` varchar(128) DEFAULT NULL,
  `opentargets_parent_id` varchar(64) DEFAULT NULL,
  `maximum_clinical_stage` varchar(128) DEFAULT NULL,
  `identity_refinement_status` varchar(128) DEFAULT NULL,
  `identity_refinement_notes` text DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`drug_id`),
  KEY `idx_drug_name` (`preferred_name`(191)),
  KEY `idx_drug_chembl` (`chembl_id`),
  KEY `idx_drug_drugbank` (`drugbank_id`),
  KEY `idx_drug_pubchem` (`pubchem_cid`),
  KEY `idx_drug_inchikey` (`standard_inchikey`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `drug_clinical_report_association`
--

DROP TABLE IF EXISTS `drug_clinical_report_association`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `drug_clinical_report_association` (
  `association_id` varchar(96) NOT NULL,
  `drug_id` varchar(64) NOT NULL,
  `clinical_report_id` varchar(64) NOT NULL,
  `drug_name` varchar(512) DEFAULT NULL,
  `source_drug_id` varchar(255) DEFAULT NULL,
  `source_drug_name` varchar(512) DEFAULT NULL,
  `match_method` varchar(255) DEFAULT NULL,
  `identity_resolution_status` varchar(128) DEFAULT NULL,
  `identity_resolution_notes` text DEFAULT NULL,
  `original_drug_id` varchar(64) DEFAULT NULL,
  `original_drug_name` varchar(512) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`association_id`),
  UNIQUE KEY `uq_drcr_natural` (`drug_id`,`clinical_report_id`),
  KEY `idx_drcr_report` (`clinical_report_id`),
  KEY `idx_drcr_status` (`identity_resolution_status`),
  CONSTRAINT `fk_drcr_drug` FOREIGN KEY (`drug_id`) REFERENCES `drug` (`drug_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_drcr_report` FOREIGN KEY (`clinical_report_id`) REFERENCES `clinical_report` (`clinical_report_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `drug_clinical_trial_association`
--

DROP TABLE IF EXISTS `drug_clinical_trial_association`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `drug_clinical_trial_association` (
  `association_id` varchar(96) NOT NULL,
  `drug_id` varchar(64) NOT NULL,
  `clinical_trial_id` varchar(32) NOT NULL,
  `drug_name` varchar(512) DEFAULT NULL,
  `identity_resolution_status` varchar(128) DEFAULT NULL,
  `identity_resolution_notes` text DEFAULT NULL,
  `original_drug_id` varchar(64) DEFAULT NULL,
  `original_drug_name` varchar(512) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`association_id`),
  UNIQUE KEY `uq_drct_natural` (`drug_id`,`clinical_trial_id`),
  KEY `idx_drct_trial` (`clinical_trial_id`),
  KEY `idx_drct_status` (`identity_resolution_status`),
  CONSTRAINT `fk_drct_drug` FOREIGN KEY (`drug_id`) REFERENCES `drug` (`drug_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_drct_trial` FOREIGN KEY (`clinical_trial_id`) REFERENCES `clinical_trial` (`clinical_trial_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `drug_form_relationship`
--

DROP TABLE IF EXISTS `drug_form_relationship`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `drug_form_relationship` (
  `drug_form_relationship_id` varchar(96) NOT NULL,
  `child_drug_id` varchar(64) NOT NULL,
  `parent_drug_id` varchar(64) NOT NULL,
  `relationship_type` varchar(128) NOT NULL,
  `child_chembl_id` varchar(64) DEFAULT NULL,
  `parent_chembl_id` varchar(64) DEFAULT NULL,
  `evidence_basis` text DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_id` varchar(255) DEFAULT NULL,
  `curation_status` varchar(128) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`drug_form_relationship_id`),
  UNIQUE KEY `uq_dfr_natural` (`child_drug_id`,`parent_drug_id`),
  KEY `idx_dfr_parent` (`parent_drug_id`),
  CONSTRAINT `fk_dfr_child` FOREIGN KEY (`child_drug_id`) REFERENCES `drug` (`drug_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dfr_parent` FOREIGN KEY (`parent_drug_id`) REFERENCES `drug` (`drug_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `drug_target_association`
--

DROP TABLE IF EXISTS `drug_target_association`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `drug_target_association` (
  `drug_target_association_id` varchar(96) NOT NULL,
  `drug_id` varchar(64) NOT NULL,
  `hgnc_id` varchar(32) NOT NULL,
  `gene_symbol` varchar(128) DEFAULT NULL,
  `ensembl_gene_id` varchar(64) DEFAULT NULL,
  `mechanism_of_action` text DEFAULT NULL,
  `action_type` varchar(128) DEFAULT NULL,
  `target_name` varchar(512) DEFAULT NULL,
  `target_type` varchar(128) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_id` varchar(255) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`drug_target_association_id`),
  KEY `idx_dta_drug` (`drug_id`),
  KEY `idx_dta_gene` (`hgnc_id`),
  KEY `idx_dta_action` (`action_type`),
  CONSTRAINT `fk_dta_drug` FOREIGN KEY (`drug_id`) REFERENCES `drug` (`drug_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_dta_gene` FOREIGN KEY (`hgnc_id`) REFERENCES `gene` (`hgnc_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `entity_external_link`
--

DROP TABLE IF EXISTS `entity_external_link`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `entity_external_link` (
  `link_id` varchar(96) NOT NULL,
  `entity_type` varchar(32) NOT NULL,
  `entity_id` varchar(96) NOT NULL,
  `resource_name` varchar(128) NOT NULL,
  `external_id` varchar(255) DEFAULT NULL,
  `url` text NOT NULL,
  `display_label` varchar(255) DEFAULT NULL,
  `display_order` int(11) NOT NULL DEFAULT 100,
  `source` varchar(128) NOT NULL DEFAULT 'generated_from_canonical_identifier',
  PRIMARY KEY (`link_id`),
  UNIQUE KEY `uq_entity_resource_url` (`entity_type`,`entity_id`,`resource_name`,`url`(255)),
  KEY `idx_external_entity` (`entity_type`,`entity_id`),
  KEY `idx_external_resource` (`resource_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `gene`
--

DROP TABLE IF EXISTS `gene`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `gene` (
  `hgnc_id` varchar(32) NOT NULL,
  `gene_symbol` varchar(128) NOT NULL,
  `gene_name` varchar(512) DEFAULT NULL,
  `ensembl_gene_id` varchar(64) DEFAULT NULL,
  `ncbi_gene_id` varchar(64) DEFAULT NULL,
  `chromosome` varchar(32) DEFAULT NULL,
  `chromosome_location` varchar(64) DEFAULT NULL,
  `gene_entity_type` varchar(128) DEFAULT NULL,
  `hgnc_status` varchar(128) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`hgnc_id`),
  UNIQUE KEY `uq_gene_symbol` (`gene_symbol`),
  KEY `idx_gene_ensembl` (`ensembl_gene_id`),
  KEY `idx_gene_ncbi` (`ncbi_gene_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `gene_category`
--

DROP TABLE IF EXISTS `gene_category`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `gene_category` (
  `gene_category_id` varchar(32) NOT NULL,
  `category_name` varchar(128) NOT NULL,
  `entity_scope` varchar(32) NOT NULL DEFAULT 'gene',
  `display_order` int(11) NOT NULL,
  PRIMARY KEY (`gene_category_id`),
  UNIQUE KEY `category_name` (`category_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `gene_category_membership`
--

DROP TABLE IF EXISTS `gene_category_membership`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `gene_category_membership` (
  `hgnc_id` varchar(32) NOT NULL,
  `gene_category_id` varchar(32) NOT NULL,
  `membership_basis` varchar(255) DEFAULT NULL,
  `source` varchar(128) NOT NULL DEFAULT 'ODDB v1',
  PRIMARY KEY (`hgnc_id`,`gene_category_id`),
  KEY `idx_gcm_category` (`gene_category_id`,`hgnc_id`),
  CONSTRAINT `fk_gcm_category` FOREIGN KEY (`gene_category_id`) REFERENCES `gene_category` (`gene_category_id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_gcm_gene` FOREIGN KEY (`hgnc_id`) REFERENCES `gene` (`hgnc_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `gene_variant_association`
--

DROP TABLE IF EXISTS `gene_variant_association`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `gene_variant_association` (
  `association_id` varchar(96) NOT NULL,
  `hgnc_id` varchar(32) NOT NULL,
  `variant_id` varchar(96) NOT NULL,
  `gene_symbol` varchar(128) DEFAULT NULL,
  `relationship_type` varchar(128) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`association_id`),
  UNIQUE KEY `uq_gva_natural` (`hgnc_id`,`variant_id`),
  KEY `idx_gva_variant` (`variant_id`),
  CONSTRAINT `fk_gva_gene` FOREIGN KEY (`hgnc_id`) REFERENCES `gene` (`hgnc_id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_gva_variant` FOREIGN KEY (`variant_id`) REFERENCES `variant` (`variant_id`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `locus`
--

DROP TABLE IF EXISTS `locus`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `locus` (
  `locus_id` varchar(96) NOT NULL,
  `locus_label` varchar(255) NOT NULL,
  `chromosome_location` varchar(128) DEFAULT NULL,
  `related_genes` text DEFAULT NULL,
  `locus_type` varchar(128) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`locus_id`),
  KEY `idx_locus_label` (`locus_label`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `oddb_import_log`
--

DROP TABLE IF EXISTS `oddb_import_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `oddb_import_log` (
  `import_log_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `release_key` varchar(128) NOT NULL,
  `table_name` varchar(128) NOT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_rows` bigint(20) unsigned NOT NULL,
  `inserted_rows` bigint(20) unsigned NOT NULL,
  `file_sha256` char(64) NOT NULL,
  `started_at` datetime NOT NULL,
  `finished_at` datetime NOT NULL,
  `status` varchar(32) NOT NULL,
  `message` text DEFAULT NULL,
  PRIMARY KEY (`import_log_id`),
  KEY `idx_import_release` (`release_key`),
  CONSTRAINT `fk_import_release` FOREIGN KEY (`release_key`) REFERENCES `oddb_release` (`release_key`) ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=26 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `oddb_release`
--

DROP TABLE IF EXISTS `oddb_release`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `oddb_release` (
  `release_key` varchar(128) NOT NULL,
  `release_type` varchar(64) NOT NULL,
  `release_path` text NOT NULL,
  `manifest_filename` varchar(255) DEFAULT NULL,
  `manifest_sha256` char(64) DEFAULT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'loaded',
  `loaded_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `notes` text DEFAULT NULL,
  PRIMARY KEY (`release_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `oddb_validation_result`
--

DROP TABLE IF EXISTS `oddb_validation_result`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `oddb_validation_result` (
  `validation_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `check_name` varchar(255) NOT NULL,
  `severity` varchar(16) NOT NULL,
  `problem_count` bigint(20) unsigned NOT NULL DEFAULT 0,
  `details` text DEFAULT NULL,
  `validated_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`validation_id`),
  KEY `idx_validation_problem` (`problem_count`)
) ENGINE=InnoDB AUTO_INCREMENT=53 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `variant`
--

DROP TABLE IF EXISTS `variant`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `variant` (
  `variant_id` varchar(96) NOT NULL,
  `clinvar_variation_id` varchar(64) DEFAULT NULL,
  `variant_name` text DEFAULT NULL,
  `variant_type` varchar(128) DEFAULT NULL,
  `clinical_significance` varchar(255) DEFAULT NULL,
  `review_status` varchar(255) DEFAULT NULL,
  `chromosome` varchar(32) DEFAULT NULL,
  `position_start` bigint(20) DEFAULT NULL,
  `position_stop` bigint(20) DEFAULT NULL,
  `reference_allele` text DEFAULT NULL,
  `alternate_allele` text DEFAULT NULL,
  `hgvs` text DEFAULT NULL,
  `rs_id` varchar(64) DEFAULT NULL,
  `assembly` varchar(64) DEFAULT NULL,
  `source` varchar(255) DEFAULT NULL,
  `source_release` varchar(128) DEFAULT NULL,
  `source_file` varchar(255) NOT NULL,
  `source_record_json` longtext NOT NULL,
  PRIMARY KEY (`variant_id`),
  UNIQUE KEY `uq_variant_clinvar` (`clinvar_variation_id`),
  KEY `idx_variant_rs` (`rs_id`),
  KEY `idx_variant_chr_pos` (`chromosome`,`position_start`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `variant_consequence`
--

DROP TABLE IF EXISTS `variant_consequence`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `variant_consequence` (
  `variant_consequence_id` varchar(96) NOT NULL,
  `variant_id` varchar(96) NOT NULL,
  `consequence_id` varchar(32) NOT NULL,
  `hgnc_id` varchar(32) DEFAULT NULL,
  `transcript_id` varchar(64) DEFAULT NULL,
  `source` varchar(128) NOT NULL DEFAULT 'ODDB source field',
  `source_value` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`variant_consequence_id`),
  UNIQUE KEY `uq_variant_consequence_gene` (`variant_id`,`consequence_id`,`hgnc_id`),
  KEY `idx_vc_consequence` (`consequence_id`,`variant_id`),
  KEY `idx_vc_gene` (`hgnc_id`),
  CONSTRAINT `fk_vc_category` FOREIGN KEY (`consequence_id`) REFERENCES `variant_consequence_category` (`consequence_id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_vc_gene` FOREIGN KEY (`hgnc_id`) REFERENCES `gene` (`hgnc_id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_vc_variant` FOREIGN KEY (`variant_id`) REFERENCES `variant` (`variant_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `variant_consequence_category`
--

DROP TABLE IF EXISTS `variant_consequence_category`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `variant_consequence_category` (
  `consequence_id` varchar(32) NOT NULL,
  `consequence_term` varchar(128) NOT NULL,
  `display_order` int(11) NOT NULL,
  PRIMARY KEY (`consequence_id`),
  UNIQUE KEY `consequence_term` (`consequence_term`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Temporary table structure for view `vw_clinical_trial_disease_drug`
--

DROP TABLE IF EXISTS `vw_clinical_trial_disease_drug`;
/*!50001 DROP VIEW IF EXISTS `vw_clinical_trial_disease_drug`*/;
SET @saved_cs_client     = @@character_set_client;
SET character_set_client = utf8;
/*!50001 CREATE VIEW `vw_clinical_trial_disease_drug` AS SELECT
 1 AS `clinical_trial_id`,
  1 AS `nct_id`,
  1 AS `title`,
  1 AS `phase`,
  1 AS `overall_status`,
  1 AS `disease_id`,
  1 AS `disease_name`,
  1 AS `drug_id`,
  1 AS `drug_name`,
  1 AS `identity_resolution_status` */;
SET character_set_client = @saved_cs_client;

--
-- Temporary table structure for view `vw_direct_therapeutic_evidence`
--

DROP TABLE IF EXISTS `vw_direct_therapeutic_evidence`;
/*!50001 DROP VIEW IF EXISTS `vw_direct_therapeutic_evidence`*/;
SET @saved_cs_client     = @@character_set_client;
SET character_set_client = utf8;
/*!50001 CREATE VIEW `vw_direct_therapeutic_evidence` AS SELECT
 1 AS `disease_drug_association_id`,
  1 AS `disease_id`,
  1 AS `disease_name`,
  1 AS `drug_id`,
  1 AS `drug_name`,
  1 AS `evidence_strength_class`,
  1 AS `disease_drug_evidence_id`,
  1 AS `evidence_subtype`,
  1 AS `clinical_report_id`,
  1 AS `clinical_trial_id`,
  1 AS `source`,
  1 AS `source_id`,
  1 AS `clinical_stage` */;
SET character_set_client = @saved_cs_client;

--
-- Temporary table structure for view `vw_drug_forms`
--

DROP TABLE IF EXISTS `vw_drug_forms`;
/*!50001 DROP VIEW IF EXISTS `vw_drug_forms`*/;
SET @saved_cs_client     = @@character_set_client;
SET character_set_client = utf8;
/*!50001 CREATE VIEW `vw_drug_forms` AS SELECT
 1 AS `drug_form_relationship_id`,
  1 AS `child_drug_id`,
  1 AS `child_drug_name`,
  1 AS `relationship_type`,
  1 AS `parent_drug_id`,
  1 AS `parent_drug_name`,
  1 AS `child_chembl_id`,
  1 AS `parent_chembl_id`,
  1 AS `evidence_basis`,
  1 AS `curation_status` */;
SET character_set_client = @saved_cs_client;

--
-- Temporary table structure for view `vw_target_overlap_discovery`
--

DROP TABLE IF EXISTS `vw_target_overlap_discovery`;
/*!50001 DROP VIEW IF EXISTS `vw_target_overlap_discovery`*/;
SET @saved_cs_client     = @@character_set_client;
SET character_set_client = utf8;
/*!50001 CREATE VIEW `vw_target_overlap_discovery` AS SELECT
 1 AS `disease_id`,
  1 AS `disease_name`,
  1 AS `drug_id`,
  1 AS `drug_name`,
  1 AS `direct_disease_drug_evidence`,
  1 AS `target_gene_count`,
  1 AS `target_genes`,
  1 AS `display_class` */;
SET character_set_client = @saved_cs_client;

--
-- Final view structure for view `vw_clinical_trial_disease_drug`
--

/*!50001 DROP VIEW IF EXISTS `vw_clinical_trial_disease_drug`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_general_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 SQL SECURITY INVOKER */
/*!50001 VIEW `vw_clinical_trial_disease_drug` AS select `ct`.`clinical_trial_id` AS `clinical_trial_id`,`ct`.`nct_id` AS `nct_id`,`ct`.`title` AS `title`,`ct`.`phase` AS `phase`,`ct`.`overall_status` AS `overall_status`,`dct`.`disease_id` AS `disease_id`,`d`.`disease_name` AS `disease_name`,`drct`.`drug_id` AS `drug_id`,`dr`.`preferred_name` AS `drug_name`,`drct`.`identity_resolution_status` AS `identity_resolution_status` from ((((`clinical_trial` `ct` join `disease_clinical_trial_association` `dct` on(`dct`.`clinical_trial_id` = `ct`.`clinical_trial_id`)) join `drug_clinical_trial_association` `drct` on(`drct`.`clinical_trial_id` = `ct`.`clinical_trial_id`)) join `disease` `d` on(`d`.`disease_id` = `dct`.`disease_id`)) join `drug` `dr` on(`dr`.`drug_id` = `drct`.`drug_id`)) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_direct_therapeutic_evidence`
--

/*!50001 DROP VIEW IF EXISTS `vw_direct_therapeutic_evidence`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_general_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 SQL SECURITY INVOKER */
/*!50001 VIEW `vw_direct_therapeutic_evidence` AS select `dda`.`disease_drug_association_id` AS `disease_drug_association_id`,`dda`.`disease_id` AS `disease_id`,`d`.`disease_name` AS `disease_name`,`dda`.`drug_id` AS `drug_id`,`dr`.`preferred_name` AS `drug_name`,`dda`.`evidence_strength_class` AS `evidence_strength_class`,`dde`.`disease_drug_evidence_id` AS `disease_drug_evidence_id`,`dde`.`evidence_subtype` AS `evidence_subtype`,`dde`.`clinical_report_id` AS `clinical_report_id`,`dde`.`clinical_trial_id` AS `clinical_trial_id`,`dde`.`source` AS `source`,`dde`.`source_id` AS `source_id`,`dde`.`clinical_stage` AS `clinical_stage` from (((`disease_drug_association` `dda` join `disease` `d` on(`d`.`disease_id` = `dda`.`disease_id`)) join `drug` `dr` on(`dr`.`drug_id` = `dda`.`drug_id`)) left join `disease_drug_evidence` `dde` on(`dde`.`disease_drug_association_id` = `dda`.`disease_drug_association_id`)) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_drug_forms`
--

/*!50001 DROP VIEW IF EXISTS `vw_drug_forms`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_general_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 SQL SECURITY INVOKER */
/*!50001 VIEW `vw_drug_forms` AS select `r`.`drug_form_relationship_id` AS `drug_form_relationship_id`,`r`.`child_drug_id` AS `child_drug_id`,`c`.`preferred_name` AS `child_drug_name`,`r`.`relationship_type` AS `relationship_type`,`r`.`parent_drug_id` AS `parent_drug_id`,`p`.`preferred_name` AS `parent_drug_name`,`r`.`child_chembl_id` AS `child_chembl_id`,`r`.`parent_chembl_id` AS `parent_chembl_id`,`r`.`evidence_basis` AS `evidence_basis`,`r`.`curation_status` AS `curation_status` from ((`drug_form_relationship` `r` join `drug` `c` on(`c`.`drug_id` = `r`.`child_drug_id`)) join `drug` `p` on(`p`.`drug_id` = `r`.`parent_drug_id`)) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_target_overlap_discovery`
--

/*!50001 DROP VIEW IF EXISTS `vw_target_overlap_discovery`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_general_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 SQL SECURITY INVOKER */
/*!50001 VIEW `vw_target_overlap_discovery` AS select `s`.`disease_id` AS `disease_id`,`d`.`disease_name` AS `disease_name`,`s`.`drug_id` AS `drug_id`,`dr`.`preferred_name` AS `drug_name`,`s`.`direct_disease_drug_evidence` AS `direct_disease_drug_evidence`,`s`.`target_gene_count` AS `target_gene_count`,`s`.`target_genes` AS `target_genes`,case when `s`.`direct_disease_drug_evidence` = 1 then 'target_overlap_plus_direct_evidence' else 'target_overlap_only_discovery' end AS `display_class` from ((`disease_drug_target_overlap_summary` `s` join `disease` `d` on(`d`.`disease_id` = `s`.`disease_id`)) join `drug` `dr` on(`dr`.`drug_id` = `s`.`drug_id`)) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-08 16:13:38
