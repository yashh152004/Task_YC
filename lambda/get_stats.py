import os
import json
import psycopg2

DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'loan_matcher_db')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres123')

def get_db_connection():
    # connect to postgres for querying dashboard counts
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def fetch_table_counts():
    print("Fetching stats from postgres...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. total users
    cursor.execute("SELECT COUNT(*) FROM users;")
    total_users = cursor.fetchone()[0]
    
    # 2. total loan products
    cursor.execute("SELECT COUNT(*) FROM loan_products;")
    total_loans = cursor.fetchone()[0]
    
    # 3. total matches
    # cursor.execute("SELECT count(id) from matches") # old query
    cursor.execute("SELECT COUNT(*) FROM matches;")
    total_matches = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    print(f"Stats fetched: Users={total_users}, Loans={total_loans}, Matches={total_matches}")
    return {
        "total_users": int(total_users),
        "total_loans": int(total_loans),
        "total_matches": int(total_matches)
    }

def lambda_handler(event, context):
    print("get_stats lambda called")
    try:
        stats = fetch_table_counts()
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "OPTIONS,GET"
            },
            "body": json.dumps(stats)
        }
    except Exception as e:
        print("Error fetching stats:", str(e))
        return {
            "statusCode": 500,
            "headers": {
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"error": str(e)})
        }
