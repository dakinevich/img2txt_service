CREATE DATABASE IF NOT EXISTS carddb;
USE carddb;
CREATE TABLE IF NOT EXISTS cards (
    id INT AUTO_INCREMENT PRIMARY KEY,
    image_filename VARCHAR(255) NOT NULL,
    description TEXT
);