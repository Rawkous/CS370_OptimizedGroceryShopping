
-- CS370_OptimizedGroceryShopping — schema.sql
-- Compatible with MySQL 8+ and MariaDB 10.5+
-- Creates database, drops old tables in FK-safe order, and recreates schema.

-- ===== Database =====
CREATE DATABASE IF NOT EXISTS SDD_003_database
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE SDD_003_database;

-- ===== Drop (reverse FK order) =====
DROP TABLE IF EXISTS saved_list_item;
DROP TABLE IF EXISTS saved_list;
DROP TABLE IF EXISTS price_history;
DROP TABLE IF EXISTS store_product;
DROP TABLE IF EXISTS product;
DROP TABLE IF EXISTS store;
DROP TABLE IF EXISTS user_location;
DROP TABLE IF EXISTS user_account;

-- ===== Users =====
CREATE TABLE user_account (
  id            CHAR(32)     NOT NULL,                 -- uuid with dashes removed
  email         VARCHAR(255) NOT NULL,
  display_name  VARCHAR(120),
  password_hash VARCHAR(255),                          -- optional (external auth ok)
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uniq_user_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===== User saved locations (home/work/etc.) =====
CREATE TABLE user_location (
  id          CHAR(32)    NOT NULL,
  user_id     CHAR(32)    NOT NULL,
  label       VARCHAR(60) NOT NULL,                    -- 'Home', 'Work', etc.
  location    POINT       NOT NULL,                    -- lon/lat in degrees
  is_default  TINYINT(1)  NOT NULL DEFAULT 0,          -- 0/1
  created_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_ul_user (user_id),
  KEY idx_ul_user_label (user_id, label),
  SPATIAL INDEX idx_user_location (location),
  CONSTRAINT fk_ul_user
    FOREIGN KEY (user_id) REFERENCES user_account(id)
    ON DELETE CASCADE
  -- NOTE: If you want "at most one default per user", enforce with app logic
  -- or a trigger. A simple UNIQUE(user_id, is_default) would also prevent
  -- multiple non-default rows, so it's not used here.
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===== Stores =====
CREATE TABLE store (
  id           CHAR(26)     NOT NULL,                  -- ULID/short id
  name         VARCHAR(120) NOT NULL,
  address      VARCHAR(200),
  city         VARCHAR(100),
  state        VARCHAR(50),
  postal_code  VARCHAR(20),
  location     POINT        NOT NULL,                  -- lon/lat in degrees
  PRIMARY KEY (id),
  KEY idx_store_city (city),
  SPATIAL INDEX idx_store_location (location)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===== Products =====
CREATE TABLE product (
  upc    VARCHAR(20)  NOT NULL,
  name   VARCHAR(200) NOT NULL,
  brand  VARCHAR(100),
  size   VARCHAR(50),
  PRIMARY KEY (upc),
  KEY idx_product_name (name),
  KEY idx_product_brand (brand)
  -- Optional (MariaDB): FULLTEXT(name, brand)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===== Prices available at stores =====
CREATE TABLE store_product (
  store_id     CHAR(26)     NOT NULL,
  product_upc  VARCHAR(20)  NOT NULL,
  price        DECIMAL(10,2),
  promo_price  DECIMAL(10,2),
  last_updated DATETIME,
  PRIMARY KEY (store_id, product_upc),
  KEY idx_sp_product (product_upc),
  CONSTRAINT fk_sp_store
    FOREIGN KEY (store_id)    REFERENCES store(id)   ON DELETE CASCADE,
  CONSTRAINT fk_sp_product
    FOREIGN KEY (product_upc) REFERENCES product(upc) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===== Historical prices (for analytics) =====
CREATE TABLE price_history (
  id          BIGINT       NOT NULL AUTO_INCREMENT,
  store_id    CHAR(26)     NOT NULL,
  product_upc VARCHAR(20)  NOT NULL,
  price       DECIMAL(10,2) NOT NULL,
  seen_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_ph_store_upc_seen (store_id, product_upc, seen_at),
  CONSTRAINT fk_ph_store
    FOREIGN KEY (store_id)    REFERENCES store(id)   ON DELETE CASCADE,
  CONSTRAINT fk_ph_product
    FOREIGN KEY (product_upc) REFERENCES product(upc) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===== Saved lists per user =====
CREATE TABLE saved_list (
  id          CHAR(32)     NOT NULL,
  user_id     CHAR(32)     NOT NULL,
  name        VARCHAR(120) NOT NULL DEFAULT 'My List',
  is_default  TINYINT(1)   NOT NULL DEFAULT 0,
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_sl_user (user_id),
  UNIQUE KEY uniq_user_list_name (user_id, name),
  CONSTRAINT fk_list_user
    FOREIGN KEY (user_id) REFERENCES user_account(id) ON DELETE CASCADE
  -- Optional: use app logic to keep only one default list per user.
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===== Line items within a list =====
CREATE TABLE saved_list_item (
  id         CHAR(32)     NOT NULL,
  list_id    CHAR(32)     NOT NULL,
  upc        VARCHAR(20)  NOT NULL,
  qty        INT          NOT NULL DEFAULT 1,
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uniq_list_item (list_id, upc),   -- prevent duplicates on same list
  KEY idx_sli_list (list_id),
  KEY idx_sli_upc (upc),
  CONSTRAINT fk_li_list
    FOREIGN KEY (list_id) REFERENCES saved_list(id) ON DELETE CASCADE,
  CONSTRAINT fk_li_product
    FOREIGN KEY (upc)     REFERENCES product(upc)   ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
