-- MariaDB-ready seed data (SRID set on INSERT using ST_GeomFromText).

USE SDD_003_database;

-- Stores
INSERT INTO store (id, name, address, city, state, postal_code, location) VALUES
('STR_000000000000000000000001', 'Market One', '123 Pine St', 'San Francisco', 'CA', '94104', ST_GeomFromText('POINT(-122.4014 37.7922)', 4326)),
('STR_000000000000000000000002', 'Budget Grocer', '456 Mission St', 'San Francisco', 'CA', '94105', ST_GeomFromText('POINT(-122.3997 37.7893)', 4326)),
('STR_000000000000000000000003', 'Neighborhood Mart', '789 3rd St', 'San Francisco', 'CA', '94107', ST_GeomFromText('POINT(-122.3950 37.7793)', 4326));

-- Products
INSERT INTO product (upc, name, brand, size) VALUES
('000111222333', '2% Milk', 'DairyPure', '1 gal'),
('000222333444', 'Large Eggs', 'Eggland''s Best', '12 ct'),
('000333444555', 'Bananas', 'Dole', '1 lb'),
('000444555666', 'White Bread', 'Wonder', '20 oz');

-- Store offers
INSERT INTO store_product (store_id, product_upc, price, promo_price, last_updated) VALUES
('STR_000000000000000000000001', '000111222333', 4.79, NULL, NOW()),
('STR_000000000000000000000002', '000111222333', 4.49, 3.99, NOW()),
('STR_000000000000000000000003', '000111222333', 4.59, NULL, NOW()),

('STR_000000000000000000000001', '000222333444', 3.89, 3.49, NOW()),
('STR_000000000000000000000002', '000222333444', 3.69, NULL, NOW()),
('STR_000000000000000000000003', '000222333444', 3.99, NULL, NOW()),

('STR_000000000000000000000001', '000333444555', 0.79, NULL, NOW()),
('STR_000000000000000000000002', '000333444555', 0.69, NULL, NOW()),
('STR_000000000000000000000003', '000333444555', 0.89, NULL, NOW()),

('STR_000000000000000000000001', '000444555666', 2.49, NULL, NOW()),
('STR_000000000000000000000002', '000444555666', 2.39, 1.99, NOW()),
('STR_000000000000000000000003', '000444555666', 2.59, NULL, NOW());

-- Example list
INSERT INTO saved_list (id, name, updated_at) VALUES (REPLACE(UUID(),'-',''), 'My List', NOW());
