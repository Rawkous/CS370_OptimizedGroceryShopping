

USE SDD_003_database;

DROP TABLE IF EXISTS saved_list_item;
DROP TABLE IF EXISTS saved_list;
DROP TABLE IF EXISTS price_history;
DROP TABLE IF EXISTS store_product;
DROP TABLE IF EXISTS product;
DROP TABLE IF EXISTS store;

CREATE TABLE store (
  id CHAR(26) PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  address VARCHAR(200),
  city VARCHAR(100),
  state VARCHAR(50),
  postal_code VARCHAR(20),
  location POINT NOT NULL,
  SPATIAL INDEX idx_store_location (location)
) ENGINE=InnoDB;

CREATE TABLE product (
  upc VARCHAR(20) PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  brand VARCHAR(100),
  size VARCHAR(50)
) ENGINE=InnoDB;

CREATE TABLE store_product (
  store_id CHAR(26) NOT NULL,
  product_upc VARCHAR(20) NOT NULL,
  price DECIMAL(10,2),
  promo_price DECIMAL(10,2),
  last_updated DATETIME,
  PRIMARY KEY (store_id, product_upc),
  CONSTRAINT fk_sp_store FOREIGN KEY (store_id) REFERENCES store(id) ON DELETE CASCADE,
  CONSTRAINT fk_sp_product FOREIGN KEY (product_upc) REFERENCES product(upc) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE price_history (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  store_id CHAR(26) NOT NULL,
  product_upc VARCHAR(20) NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX (store_id, product_upc, seen_at),
  CONSTRAINT fk_ph_store FOREIGN KEY (store_id) REFERENCES store(id) ON DELETE CASCADE,
  CONSTRAINT fk_ph_product FOREIGN KEY (product_upc) REFERENCES product(upc) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE saved_list (
  id CHAR(32) PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  updated_at DATETIME NOT NULL
) ENGINE=InnoDB;

CREATE TABLE saved_list_item (
  id CHAR(32) PRIMARY KEY,
  list_id CHAR(32) NOT NULL,
  upc VARCHAR(20) NOT NULL,
  qty INT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_li_list FOREIGN KEY (list_id) REFERENCES saved_list(id) ON DELETE CASCADE
) ENGINE=InnoDB;
