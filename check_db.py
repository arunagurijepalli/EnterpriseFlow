import sqlite3

conn = sqlite3.connect("data/company.db")

print("Companies:")
print(conn.execute("SELECT company_id, name, domain FROM companies").fetchall())

print("\nTables:")
print(conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())

conn.close()
