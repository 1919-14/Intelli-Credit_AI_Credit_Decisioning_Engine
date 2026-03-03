CREATE DATABASE  IF NOT EXISTS `intelli_credit` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;
USE `intelli_credit`;
-- MySQL dump 10.13  Distrib 8.0.44, for Win64 (x86_64)
--
-- Host: localhost    Database: intelli_credit
-- ------------------------------------------------------
-- Server version	8.0.44

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `applications`
--

DROP TABLE IF EXISTS `applications`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `applications` (
  `id` int NOT NULL AUTO_INCREMENT,
  `case_id` varchar(50) NOT NULL,
  `company_name` varchar(200) NOT NULL,
  `status` varchar(30) DEFAULT 'pending',
  `current_layer` int DEFAULT '0',
  `layer2_output` longtext,
  `risk_score` float DEFAULT NULL,
  `decision` varchar(50) DEFAULT NULL,
  `decision_conditions` text,
  `created_by` int NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `completed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `case_id` (`case_id`),
  KEY `created_by` (`created_by`),
  CONSTRAINT `applications_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `applications`
--

LOCK TABLES `applications` WRITE;
/*!40000 ALTER TABLE `applications` DISABLE KEYS */;
INSERT INTO `applications` VALUES (1,'APP-2025-00001','SAI','pending',0,NULL,NULL,NULL,NULL,1,'2026-03-03 23:25:48',NULL),(2,'APP-2025-00002','SAI','pending',0,NULL,NULL,NULL,NULL,1,'2026-03-04 00:10:32',NULL),(3,'APP-2025-00003','SAI','pending',0,NULL,NULL,NULL,NULL,1,'2026-03-04 00:12:30',NULL),(4,'APP-2025-00004','SAI','completed',3,'{\n  \"meta\": {\n    \"case_id\": \"APP-2025-00004\",\n    \"company_name\": \"SAI\",\n    \"extraction_timestamp\": \"2026-03-03T18:45:09.576751Z\",\n    \"schema_version\": \"2.1\",\n    \"pipeline_version\": \"1.0.0\",\n    \"llm_model\": \"meta-llama/llama-4-scout-17b-16e-instruct\",\n    \"llm_provider\": \"groq\",\n    \"ocr_engine\": \"pymupdf_primary_easyocr_fallback\",\n    \"documents_processed\": {\n      \"SRC_UNKNOWN\": {\n        \"filename\": \"frm_download_file.pdf\",\n        \"file_hash\": \"sha256:39d9cd\",\n        \"pages\": 7,\n        \"ocr_used\": false,\n        \"extraction_confidence\": 0.9\n      }\n    },\n    \"extraction_summary\": {\n      \"total_fields_attempted\": 0,\n      \"fields_extracted\": 0,\n      \"fields_null\": 0,\n      \"fields_low_confidence\": 0,\n      \"human_review_queue\": 0,\n      \"overall_quality_score\": 0.0\n    }\n  },\n  \"extracted\": {\n    \"SRC_GST\": null,\n    \"SRC_ITR\": null,\n    \"SRC_BANK\": null,\n    \"SRC_UNKNOWN\": {}\n  }\n}',NULL,NULL,NULL,1,'2026-03-04 00:12:51','2026-03-04 00:15:09');
/*!40000 ALTER TABLE `applications` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `audit_logs`
--

DROP TABLE IF EXISTS `audit_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `audit_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `actor_id` int NOT NULL,
  `action` varchar(100) NOT NULL,
  `target` varchar(200) DEFAULT NULL,
  `details` json DEFAULT NULL,
  `timestamp` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `actor_id` (`actor_id`),
  KEY `action` (`action`)
) ENGINE=InnoDB AUTO_INCREMENT=80 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `audit_logs`
--

LOCK TABLES `audit_logs` WRITE;
/*!40000 ALTER TABLE `audit_logs` DISABLE KEYS */;
INSERT INTO `audit_logs` VALUES (1,1,'LOGIN','admin',NULL,'2026-03-03 13:44:31'),(2,1,'REORDER_ROLES',NULL,'{\"order\": [\"SUPER_ADMIN\", \"VIEWER\", \"CREDIT_ANALYST\"]}','2026-03-03 13:45:36'),(3,1,'REORDER_ROLES',NULL,'{\"order\": [\"SUPER_ADMIN\", \"CREDIT_ANALYST\", \"VIEWER\"]}','2026-03-03 13:45:38'),(4,1,'CREATE_ROLE','TEST',NULL,'2026-03-03 13:46:13'),(5,1,'CREATE_USER','test','{\"role\": \"TEST\"}','2026-03-03 13:46:30'),(6,2,'LOGIN','test',NULL,'2026-03-03 13:46:53'),(7,1,'LOGIN','admin',NULL,'2026-03-03 13:48:00'),(8,2,'LOGOUT',NULL,NULL,'2026-03-03 14:22:44'),(9,1,'LOGIN','admin',NULL,'2026-03-03 14:22:51'),(10,1,'LOGOUT',NULL,NULL,'2026-03-03 14:27:58'),(11,1,'LOGOUT',NULL,NULL,'2026-03-03 14:27:58'),(12,2,'LOGIN','test',NULL,'2026-03-03 14:28:03'),(13,2,'LOGOUT',NULL,NULL,'2026-03-03 14:28:31'),(14,1,'LOGIN','admin',NULL,'2026-03-03 14:28:50'),(15,1,'LOGOUT',NULL,NULL,'2026-03-03 14:28:58'),(16,2,'LOGIN','test',NULL,'2026-03-03 14:29:05'),(17,2,'LOGOUT',NULL,NULL,'2026-03-03 14:29:12'),(18,1,'LOGIN','admin',NULL,'2026-03-03 22:45:32'),(19,1,'LOGOUT',NULL,NULL,'2026-03-03 23:16:24'),(20,2,'LOGIN','test',NULL,'2026-03-03 23:16:29'),(21,2,'LOGOUT',NULL,NULL,'2026-03-03 23:16:40'),(22,1,'LOGIN','admin',NULL,'2026-03-03 23:16:46'),(23,1,'LOGOUT',NULL,NULL,'2026-03-03 23:18:19'),(24,1,'LOGIN','admin',NULL,'2026-03-03 23:18:38'),(25,1,'LOGOUT',NULL,NULL,'2026-03-03 23:24:50'),(26,1,'LOGIN','admin',NULL,'2026-03-03 23:25:15'),(27,1,'CREATE_APPLICATION','APP-2025-00001',NULL,'2026-03-03 23:25:48'),(28,1,'CREATE_ROLE','TEST2',NULL,'2026-03-03 23:30:09'),(29,1,'LOGOUT',NULL,NULL,'2026-03-03 23:31:54'),(30,2,'LOGIN','test',NULL,'2026-03-03 23:32:00'),(31,2,'LOGOUT',NULL,NULL,'2026-03-03 23:32:15'),(32,1,'LOGIN','admin',NULL,'2026-03-03 23:32:22'),(33,1,'REORDER_ROLES',NULL,'{\"order\": [\"SUPER_ADMIN\", \"TEST2\", \"CREDIT_ANALYST\", \"VIEWER\", \"TEST\"]}','2026-03-03 23:38:11'),(34,1,'REORDER_ROLES',NULL,'{\"order\": [\"SUPER_ADMIN\", \"CREDIT_ANALYST\", \"VIEWER\", \"TEST\", \"TEST2\"]}','2026-03-03 23:38:24'),(35,1,'REORDER_ROLES',NULL,'{\"order\": [\"SUPER_ADMIN\", \"TEST2\", \"CREDIT_ANALYST\", \"VIEWER\", \"TEST\"]}','2026-03-03 23:38:55'),(36,1,'DELETE_ROLE','TEST','{\"user_count\": 1, \"reassigned_to\": \"CREDIT_ANALYST\"}','2026-03-03 23:39:40'),(37,1,'LOGOUT',NULL,NULL,'2026-03-03 23:39:55'),(38,2,'LOGIN','test',NULL,'2026-03-03 23:40:00'),(39,2,'LOGOUT',NULL,NULL,'2026-03-03 23:40:23'),(40,1,'LOGIN','admin',NULL,'2026-03-03 23:40:38'),(41,1,'CREATE_USER','test2','{\"role\": \"TEST2\"}','2026-03-03 23:40:58'),(42,1,'LOGOUT',NULL,NULL,'2026-03-03 23:41:03'),(43,7,'LOGIN','test2',NULL,'2026-03-03 23:41:09'),(44,7,'LOGOUT',NULL,NULL,'2026-03-03 23:41:30'),(45,1,'LOGIN','admin',NULL,'2026-03-03 23:41:35'),(46,1,'UPDATE_ROLE','role:TEST2',NULL,'2026-03-03 23:44:37'),(47,1,'LOGOUT',NULL,NULL,'2026-03-03 23:44:49'),(48,7,'LOGIN','test2',NULL,'2026-03-03 23:44:54'),(49,7,'LOGOUT',NULL,NULL,'2026-03-03 23:45:40'),(50,1,'LOGIN','admin',NULL,'2026-03-03 23:45:46'),(51,1,'LOGOUT',NULL,NULL,'2026-03-03 23:50:01'),(52,7,'LOGIN','test2',NULL,'2026-03-03 23:50:08'),(53,7,'LOGOUT',NULL,NULL,'2026-03-03 23:50:22'),(54,1,'LOGIN','admin',NULL,'2026-03-03 23:50:30'),(55,1,'LOGOUT',NULL,NULL,'2026-03-03 23:54:08'),(56,7,'LOGIN','test2',NULL,'2026-03-03 23:54:16'),(57,7,'LOGOUT',NULL,NULL,'2026-03-03 23:54:29'),(58,1,'LOGIN','admin',NULL,'2026-03-03 23:54:35'),(59,1,'LOGOUT',NULL,NULL,'2026-03-03 23:55:24'),(60,7,'LOGIN','test2',NULL,'2026-03-03 23:55:30'),(61,7,'LOGOUT',NULL,NULL,'2026-03-03 23:57:17'),(62,1,'LOGIN','admin',NULL,'2026-03-03 23:57:24'),(63,1,'LOGOUT',NULL,NULL,'2026-03-03 23:59:12'),(64,7,'LOGIN','test2',NULL,'2026-03-03 23:59:20'),(65,7,'CREATE_USER','sai','{\"role\": \"VIEWER\"}','2026-03-03 23:59:55'),(66,7,'LOGOUT',NULL,NULL,'2026-03-04 00:00:02'),(67,7,'LOGIN','test2',NULL,'2026-03-04 00:00:33'),(68,7,'DELETE_USER','8',NULL,'2026-03-04 00:00:46'),(69,7,'CREATE_USER','sai','{\"role\": \"VIEWER\"}','2026-03-04 00:00:55'),(70,7,'LOGOUT',NULL,NULL,'2026-03-04 00:00:59'),(71,9,'LOGIN','sai',NULL,'2026-03-04 00:01:04'),(72,9,'LOGOUT',NULL,NULL,'2026-03-04 00:01:45'),(73,1,'LOGIN','admin',NULL,'2026-03-04 00:09:44'),(74,1,'CREATE_APPLICATION','APP-2025-00002',NULL,'2026-03-04 00:10:32'),(75,1,'UPLOAD_FILES','APP-2025-00002','{\"count\": 1}','2026-03-04 00:10:34'),(76,1,'CREATE_APPLICATION','APP-2025-00003',NULL,'2026-03-04 00:12:30'),(77,1,'CREATE_APPLICATION','APP-2025-00004',NULL,'2026-03-04 00:12:51'),(78,1,'UPLOAD_FILES','APP-2025-00004','{\"count\": 1}','2026-03-04 00:13:09'),(79,1,'HITL_CONFIRM','APP-2025-00004','{\"corrections\": 1}','2026-03-04 00:14:39');
/*!40000 ALTER TABLE `audit_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `documents`
--

DROP TABLE IF EXISTS `documents`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `documents` (
  `id` int NOT NULL AUTO_INCREMENT,
  `application_id` int NOT NULL,
  `filename` varchar(255) NOT NULL,
  `file_type` varchar(10) NOT NULL,
  `file_size` int DEFAULT '0',
  `detected_category` varchar(30) DEFAULT NULL,
  `status` varchar(20) DEFAULT 'pending',
  `file_path` varchar(500) NOT NULL,
  `uploaded_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `application_id` (`application_id`),
  CONSTRAINT `documents_ibfk_1` FOREIGN KEY (`application_id`) REFERENCES `applications` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `documents`
--

LOCK TABLES `documents` WRITE;
/*!40000 ALTER TABLE `documents` DISABLE KEYS */;
INSERT INTO `documents` VALUES (1,2,'frm_download_file.pdf','PDF',50583,'SRC_UNKNOWN','done','C:\\Users\\saina\\Videos\\AIML Hack\\static\\uploads\\2\\frm_download_file.pdf','2026-03-04 00:10:34'),(2,4,'frm_download_file.pdf','PDF',50583,'SRC_UNKNOWN','done','C:\\Users\\saina\\Videos\\AIML Hack\\static\\uploads\\4\\frm_download_file.pdf','2026-03-04 00:13:09');
/*!40000 ALTER TABLE `documents` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `name` varchar(50) NOT NULL,
  `default_permissions` json NOT NULL,
  `allowed_child_roles` json NOT NULL,
  `hierarchy_order` int DEFAULT '999',
  `description` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `roles`
--

LOCK TABLES `roles` WRITE;
/*!40000 ALTER TABLE `roles` DISABLE KEYS */;
INSERT INTO `roles` VALUES ('CREDIT_ANALYST','[\"CREATE_APP\", \"RUN_PIPELINE\", \"VIEW_RESULTS\", \"VIEW_HISTORY\", \"VIEW_APP\"]','[\"VIEWER\"]',3,'Credit Analyst'),('SUPER_ADMIN','[\"*\"]','[\"CREDIT_ANALYST\", \"VIEWER\"]',1,'Full System Control'),('TEST2','[\"CREATE_APP\", \"VIEW_APP\", \"DELETE_APP\", \"VIEW_RESULTS\", \"MANAGE_USERS\", \"VIEW_HISTORY\", \"VIEW_AUDIT_LOGS\", \"EDIT_USERS\", \"EDIT_ROLES\"]','[]',2,''),('VIEWER','[\"VIEW_RESULTS\", \"VIEW_HISTORY\", \"VIEW_APP\"]','[]',4,'Read-Only Viewer');
/*!40000 ALTER TABLE `roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(100) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `full_name` varchar(200) NOT NULL,
  `role` varchar(50) NOT NULL,
  `custom_permissions` json DEFAULT NULL,
  `created_by` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  KEY `role` (`role`),
  CONSTRAINT `users_ibfk_1` FOREIGN KEY (`role`) REFERENCES `roles` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'admin','scrypt:32768:8:1$o12EuRENv8wPI9rg$70281d12749e69e3576f477176a3dad0c30c6e2ff343be24b1ef06907854be3ba4c8bc65e88a252480b82fd55e4f43e9d3ea48700282f358eff3cb762dafd104','Super Administrator','SUPER_ADMIN',NULL,NULL,'2026-03-03 13:44:14'),(2,'test','scrypt:32768:8:1$6NPv4BE73d3BfgzN$dbba9c7e3e0a686d2bca5a2bef453a3279a80beaba0a1e4932d5b34ac84385d63adf3ccb3d44ceb01438b37e91e116e2ddbb63fc2a9618d840145ddb37a9d5f7','ss','CREDIT_ANALYST',NULL,1,'2026-03-03 13:46:30'),(7,'test2','scrypt:32768:8:1$HleCXEjMlZbI7LSu$df66c90c8cafac38a0282e190b567e0e15054914c21d81b00f3cef795d333856f82e7570014678be18e6f62aeb1e4a42f715b51407299938ea5beb3fb641f26f','sujeet','TEST2',NULL,1,'2026-03-03 23:40:58'),(9,'sai','scrypt:32768:8:1$pACjKJrkOiJZTsra$d8e49bab58e7b09425117de89c96fa09fadc8e76f1de2c97eee94c20705b630b52d3bbeaa450addd6113e70627299368ea7799981d8e1ef0498496e48b6d2a09','sai','VIEWER',NULL,7,'2026-03-04 00:00:55');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-03-04  0:42:38
