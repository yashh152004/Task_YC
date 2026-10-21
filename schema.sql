-- 7th Sem CSE Internship Project: Smart Loan Matching System
-- Database Schema for PostgreSQL

-- Drop tables if resetting
-- DROP TABLE IF EXISTS matches;
-- DROP TABLE IF EXISTS loan_products;
-- DROP TABLE IF EXISTS users;

-- 1. Users table (populated from S3 CSV upload via Lambda)
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    monthly_income NUMERIC(12, 2) NOT NULL,
    credit_score INT NOT NULL,
    employment_status VARCHAR(50) NOT NULL,
    age INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Loan products table (populated via n8n scraper / backup JSON)
CREATE TABLE IF NOT EXISTS loan_products (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(150) NOT NULL,
    bank_name VARCHAR(100) NOT NULL,
    interest_rate NUMERIC(5, 2) NOT NULL,
    min_income NUMERIC(12, 2) NOT NULL,
    min_credit_score INT NOT NULL,
    employment_types VARCHAR(255) NOT NULL, -- e.g. "Salaried, Self-Employed"
    source_url TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_bank_product UNIQUE (bank_name, product_name)
);

-- 3. Matches table (stores final matched user-loan pairs)
CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(user_id) ON DELETE CASCADE,
    product_id INT REFERENCES loan_products(product_id) ON DELETE CASCADE,
    matched_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_user_product_match UNIQUE (user_id, product_id)
);

-- Sample initial loan products so system works right after spin up
INSERT INTO loan_products (product_name, bank_name, interest_rate, min_income, min_credit_score, employment_types, source_url)
VALUES 
('Express Personal Loan', 'HDFC Bank', 10.50, 25000.00, 700, 'Salaried', 'https://www.hdfcbank.com/personal-loan'),
('Quick Cash Loan', 'Bajaj Finserv', 12.99, 20000.00, 650, 'Salaried, Self-Employed', 'https://www.bajajfinserv.in/personal-loan'),
('Flexi Business Loan', 'ICICI Bank', 11.25, 45000.00, 720, 'Self-Employed, Business', 'https://www.icicibank.com/business-loan'),
('Youth Career Loan', 'SBI', 9.80, 18000.00, 600, 'Salaried', 'https://sbi.co.in/personal-loan')
ON CONFLICT (bank_name, product_name) DO NOTHING;
