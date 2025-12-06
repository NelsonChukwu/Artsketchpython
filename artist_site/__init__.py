"""
Project init for Hybrid Artistic Engine.
Ensures PyMySQL can stand in for MySQLdb when using MySQL.
"""

try:
    import pymysql

    pymysql.install_as_MySQLdb()
except Exception:
    # Safe to ignore when MySQL is not in use.
    pass
