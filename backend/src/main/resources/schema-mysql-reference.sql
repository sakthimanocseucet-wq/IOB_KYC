CREATE DATABASE IF NOT EXISTS iob_kyc DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE iob_kyc;

-- Users table (customers only)
CREATE TABLE users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20),
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    role VARCHAR(20) NOT NULL DEFAULT 'USER',
    is_active BOOLEAN DEFAULT TRUE,
    is_locked BOOLEAN DEFAULT FALSE,
    failed_attempts INT DEFAULT 0,
    lock_time TIMESTAMP NULL,
    last_login TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_email (email),
    INDEX idx_role (role)
);

-- Employees table (admin, manager, officer)
CREATE TABLE employees (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    employee_id VARCHAR(20) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20),
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    role ENUM('ADMIN', 'MANAGER', 'OFFICER') NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_locked BOOLEAN DEFAULT FALSE,
    failed_attempts INT DEFAULT 0,
    lock_time TIMESTAMP NULL,
    last_login TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_email (email),
    INDEX idx_employee_id (employee_id),
    INDEX idx_role (role)
);

-- KYC Applications
CREATE TABLE kyc_applications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    application_ref VARCHAR(20) UNIQUE NOT NULL,
    doc_type ENUM('AADHAAR', 'PAN') NOT NULL,
    doc_file_path VARCHAR(500),
    selfie_file_path VARCHAR(500),
    ocr_name VARCHAR(200),
    ocr_dob DATE,
    ocr_id_number VARCHAR(100),
    ocr_address TEXT,
    face_match_percentage DECIMAL(5,2),
    liveness_passed BOOLEAN DEFAULT FALSE,
    risk_score INT DEFAULT 0,
    risk_level ENUM('LOW', 'MEDIUM', 'HIGH') DEFAULT 'LOW',
    status ENUM('DRAFT', 'PENDING', 'UNDER_REVIEW', 'APPROVED', 'REJECTED') DEFAULT 'DRAFT',
    reviewed_by BIGINT,
    review_notes TEXT,
    submitted_at TIMESTAMP NULL,
    reviewed_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (reviewed_by) REFERENCES employees(id),
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_risk_level (risk_level)
);

-- Risk Scores (detailed breakdown)
CREATE TABLE risk_scores (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    application_id BIGINT NOT NULL,
    device_fingerprint_score INT DEFAULT 0,
    ip_reputation_score INT DEFAULT 0,
    geolocation_score INT DEFAULT 0,
    face_match_score INT DEFAULT 0,
    behavioral_score INT DEFAULT 0,
    total_score INT DEFAULT 0,
    assessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (application_id) REFERENCES kyc_applications(id)
);

-- Device Fingerprints
CREATE TABLE device_fingerprints (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT,
    fingerprint_hash VARCHAR(255) NOT NULL,
    device_name VARCHAR(200),
    os VARCHAR(100),
    browser VARCHAR(100),
    ip_address VARCHAR(45),
    user_agent TEXT,
    is_trusted BOOLEAN DEFAULT FALSE,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_fingerprint (fingerprint_hash)
);

-- Sessions
CREATE TABLE sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    session_token VARCHAR(500) NOT NULL,
    device_fingerprint_id BIGINT,
    ip_address VARCHAR(45),
    is_active BOOLEAN DEFAULT TRUE,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_user_id (user_id),
    INDEX idx_token (session_token)
);

-- Audit Logs
CREATE TABLE audit_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id BIGINT,
    details TEXT,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_action (action),
    INDEX idx_created_at (created_at)
);

-- Fraud Alerts
CREATE TABLE fraud_alerts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    application_id BIGINT,
    alert_type ENUM('MULTIPLE_ACCOUNTS', 'RAPID_LOGIN', 'GEO_ANOMALY', 'DEVICE_MISMATCH', 'SUSPICIOUS_FILE', 'DEEPFAKE_DETECTED'),
    severity ENUM('LOW', 'MEDIUM', 'HIGH') DEFAULT 'MEDIUM',
    description TEXT NOT NULL,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_by BIGINT,
    resolved_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (application_id) REFERENCES kyc_applications(id),
    INDEX idx_severity (severity),
    INDEX idx_resolved (is_resolved)
);

-- OTP Codes
CREATE TABLE otp_codes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT,
    identifier VARCHAR(255) NOT NULL,
    otp_code VARCHAR(6) NOT NULL,
    purpose ENUM('LOGIN', 'REGISTER', 'KYC', 'PASSWORD_RESET') NOT NULL,
    is_used BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_identifier (identifier),
    INDEX idx_otp_code (otp_code)
);

-- Notifications
CREATE TABLE notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    type ENUM('SMS', 'EMAIL', 'IN_APP') NOT NULL,
    subject VARCHAR(200),
    message TEXT NOT NULL,
    status ENUM('PENDING', 'SENT', 'FAILED') DEFAULT 'PENDING',
    sent_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_status (status)
);
