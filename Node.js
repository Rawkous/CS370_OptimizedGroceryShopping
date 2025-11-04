import 'dotenv/config';
import mysql from 'mysql2/promise';

const conn = await mysql.createConnection({
  host: process.env.DB_HOST || 'blue.cs.sonoma.edu',
  port: Number(process.env.DB_PORT || 3306),
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
  connectTimeout: 10000
  // ssl: { ca: fs.readFileSync('path/to/ca.pem') } // if Blue requires TLS
});

const [rows] = await conn.execute('SELECT 1 AS ok');
console.log(rows);
await conn.end();
