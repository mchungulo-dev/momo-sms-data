-- -------------------------------------------------------
-- database_setup.sql
-- The Database Schema we built for MoMo SMS Transaction Processing System 
-- -------------------------------------------------------

DROP DATABASE IF EXISTS momo_sms_db;
CREATE DATABASE momo_sms_db;
USE momo_sms_db;

-- ------------------------------------------------------------
-- Table: users
-- ------------------------------------------------------------
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique identifier for a user (sender/receiver)',
    full_name VARCHAR(100) NOT NULL COMMENT 'Full name of the user',
    phone_number VARCHAR(15) NOT NULL UNIQUE COMMENT 'MoMo-registered phone number',
    user_type ENUM('CUSTOMER','AGENT','MERCHANT') NOT NULL DEFAULT 'CUSTOMER' COMMENT 'Role of the user in the MoMo network',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation timestamp',
    CONSTRAINT chk_phone_format CHECK (phone_number REGEXP '^[+]?[0-9]{9,15}$')
) ENGINE=InnoDB COMMENT='Registered MoMo users: customers, agents, and merchants';

-- ------------------------------------------------------------
-- Table: transaction_categories
-- ------------------------------------------------------------
CREATE TABLE transaction_categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique identifier for a transaction category',
    category_name VARCHAR(50) NOT NULL UNIQUE COMMENT 'e.g. Transfer, Airtime, Bill Payment, Withdrawal',
    description VARCHAR(255) COMMENT 'Human-readable explanation of the category'
) ENGINE=InnoDB COMMENT='Lookup table for transaction category tags';

-- ------------------------------------------------------------
-- Table: transactions
-- ------------------------------------------------------------
CREATE TABLE transactions (
    transaction_id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique identifier for a transaction',
    sender_id INT NULL COMMENT 'FK to users; NULL when the SMS has no identifiable sender (e.g. deposit)',
    receiver_id INT NULL COMMENT 'FK to users; NULL when the SMS has no identifiable receiver (e.g. withdrawal)',
    amount DECIMAL(12,2) NOT NULL COMMENT 'Transaction amount in local currency',
    fee DECIMAL(8,2) NOT NULL DEFAULT 0.00 COMMENT 'Transaction fee charged',
    created_at DATETIME NOT NULL COMMENT 'Timestamp the transaction occurred, parsed from the SMS',
    raw_sms_body TEXT COMMENT 'Original SMS text this record was parsed from',
    CONSTRAINT fk_transactions_sender FOREIGN KEY (sender_id) REFERENCES users(user_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_transactions_receiver FOREIGN KEY (receiver_id) REFERENCES users(user_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT chk_amount_positive CHECK (amount > 0),
    CONSTRAINT chk_fee_non_negative CHECK (fee >= 0)
) ENGINE=InnoDB COMMENT='Core MoMo transaction records parsed from SMS data';

-- ------------------------------------------------------------
-- Table: transaction_has_categories (junction - resolves M:N)
-- ------------------------------------------------------------
CREATE TABLE transaction_has_categories (
    transaction_id BIGINT NOT NULL COMMENT 'FK to transactions',
    category_id INT NOT NULL COMMENT 'FK to transaction_categories',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When this category tag was applied',
    PRIMARY KEY (transaction_id, category_id),
    CONSTRAINT fk_thc_transaction FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_thc_category FOREIGN KEY (category_id) REFERENCES transaction_categories(category_id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB COMMENT='Junction table resolving the M:N relationship between transactions and categories';

-- ------------------------------------------------------------
-- Table: system_logs
-- ------------------------------------------------------------
CREATE TABLE system_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique identifier for a log entry',
    user_id INT NULL COMMENT 'FK to users; NULL when no user could be identified',
    transaction_id BIGINT NULL COMMENT 'FK to transactions; NULL for dead-letter entries with no created transaction',
    log_level ENUM('INFO','WARNING','ERROR') NOT NULL DEFAULT 'INFO' COMMENT 'Severity of the log entry',
    action_performed VARCHAR(100) NOT NULL COMMENT 'e.g. PARSE, CLEAN, CATEGORIZE, LOAD',
    status ENUM('SUCCESS','FAILED','SKIPPED') NOT NULL COMMENT 'Outcome of the ETL step',
    error_message TEXT COMMENT 'Error detail when status is FAILED',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When the log entry was recorded',
    CONSTRAINT fk_logs_user FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_logs_transaction FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB COMMENT='ETL processing log, including dead-letter (failed parse) entries';

-- -------------------------------------------------------
-- INDEXES for performance
-- -------------------------------------------------------
CREATE INDEX idx_transactions_sender ON transactions(sender_id);
CREATE INDEX idx_transactions_receiver ON transactions(receiver_id);
CREATE INDEX idx_transactions_created_at ON transactions(created_at);
CREATE INDEX idx_logs_status ON system_logs(status);
CREATE INDEX idx_logs_transaction ON system_logs(transaction_id);
CREATE INDEX idx_users_phone ON users(phone_number);

-- -------------------------------------------------------
-- HERE WE INSERT SAMPLE DATA (DML)
-- -------------------------------------------------------
-- Users
INSERT INTO users (full_name, phone_number, user_type) VALUES
('Mwiza Uwase', '+250788111222', 'CUSTOMER'),
('Butera Jean Aime', '+250788333444', 'CUSTOMER'),
('DELUXE Supermarket', '+250788777888', 'MERCHANT'),
('Dushime Erica', '+250788555666', 'AGENT'),
('Mugwiza Melissa', '+250788999000', 'CUSTOMER');

-- Transaction Categories
INSERT INTO transaction_categories (category_name, description) VALUES
('Transfer', 'Peer-to-peer money transfer'),
('Airtime', 'Mobile airtime purchase'),
('Bill Payment', 'Utility or service bill payment'),
('Withdrawal', 'Cash withdrawal from an agent'),
('Deposit', 'Cash deposit into a MoMo account'),
('International', 'Cross-border transfer tag');

