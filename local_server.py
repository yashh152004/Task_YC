"""
Local Development Server for Testing (7th Sem Project)
Run: python local_server.py
Opens frontend on http://localhost:8000 and mocks or proxies Lambda endpoints.
"""

import os
import json
import csv
import io
import subprocess
import http.server
import socketserver
import urllib.parse
import urllib.request
import importlib

PORT = 8000

# Try importing lambda modules dynamically
get_stats_mod = None
ingest_mod = None
try:
    get_stats_mod = importlib.import_module("lambda.get_stats")
except Exception:
    pass

try:
    ingest_mod = importlib.import_module("lambda.ingest_users")
except Exception:
    pass

def query_postgres_stats():
    # 1. Try python module if psycopg2 exists
    if get_stats_mod:
        try:
            return get_stats_mod.fetch_table_counts()
        except Exception:
            pass

    # 2. Seamless fallback: query running Docker container
    try:
        cmd = ["docker", "exec", "loan_postgres", "psql", "-U", "postgres", "-d", "loan_matcher_db", "-t", "-c",
               "SELECT (SELECT count(*) FROM users) || ',' || (SELECT count(*) FROM loan_products) || ',' || (SELECT count(*) FROM matches);"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            parts = result.stdout.strip().split(',')
            return {
                "total_users": int(parts[0].strip()),
                "total_loans": int(parts[1].strip()),
                "total_matches": int(parts[2].strip())
            }
    except Exception as e:
        print(f"Error querying docker postgres stats: {e}")

    return {"total_users": 0, "total_loans": 0, "total_matches": 0}

def ingest_csv_to_postgres(body_text):
    inserted_count = 0
    # Try python ingest module first
    if ingest_mod:
        try:
            return ingest_mod.parse_csv_and_insert(body_text)
        except Exception:
            pass

    # Fallback via Docker
    try:
        reader = csv.DictReader(io.StringIO(body_text))
        sql_statements = []
        for row in reader:
            email = row.get('email', '').strip().replace("'", "''")
            income = float(row.get('monthly_income', 0))
            credit = int(row.get('credit_score', 0))
            status = row.get('employment_status', 'Salaried').strip().replace("'", "''")
            age = int(row.get('age', 25))
            sql = f"INSERT INTO users (email, monthly_income, credit_score, employment_status, age) VALUES ('{email}', {income}, {credit}, '{status}', {age}) ON CONFLICT (email) DO NOTHING;"
            sql_statements.append(sql)
            inserted_count += 1

        if sql_statements:
            full_sql = "\n".join(sql_statements)
            proc = subprocess.run(
                ["docker", "exec", "-i", "loan_postgres", "psql", "-U", "postgres", "-d", "loan_matcher_db"],
                input=full_sql,
                capture_output=True,
                text=True,
                timeout=10
            )
            print(f"Postgres batch insert: {inserted_count} rows submitted.")
    except Exception as err:
        print(f"Error inserting CSV into docker postgres: {err}")

    # Trigger n8n webhook
    for webhook_url in ["http://localhost:5678/webhook/new-users", "http://localhost:5678/webhook-test/new-users"]:
        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps({"status": "success", "total_inserted": inserted_count}).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            resp = urllib.request.urlopen(req, timeout=3)
            print(f"n8n webhook triggered ({webhook_url})! Response: {resp.getcode()}")
            break
        except Exception:
            pass

    return inserted_count

class LocalDemoHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        # Route: /stats
        if parsed_path.path == '/stats':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            data = query_postgres_stats()
            self.wfile.write(json.dumps(data).encode('utf-8'))
            return

        # Route: /recent-matches (preview formatted notification emails)
        if parsed_path.path == '/recent-matches':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                cmd = ["docker", "exec", "loan_postgres", "psql", "-U", "postgres", "-d", "loan_matcher_db", "-t", "-c",
                       "SELECT u.user_id, u.email, string_agg(lp.bank_name || ' (' || lp.product_name || ') @ ' || lp.interest_rate || '%', ' and ') FROM matches m JOIN users u ON m.user_id = u.user_id JOIN loan_products lp ON m.product_id = lp.product_id GROUP BY u.user_id, u.email LIMIT 3;"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                matches_list = []
                for line in res.stdout.strip().split("\n"):
                    if "|" in line:
                        parts = [p.strip() for p in line.split("|")]
                        if len(parts) >= 3:
                            uid, email, loans = parts[0], parts[1], parts[2]
                            body = f"Hi User {uid},\n\nCongratulations! You are eligible for:\n{loans}\n\nBest regards,\nSmart Loan Matcher Team"
                            matches_list.append({"user_id": uid, "email": email, "email_body": body})
                self.wfile.write(json.dumps(matches_list).encode('utf-8'))
            except Exception as err:
                self.wfile.write(json.dumps([]).encode('utf-8'))
            return

        # Route: /presigned-url
        if parsed_path.path == '/presigned-url':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response_payload = {
                "upload_url": f"http://localhost:{PORT}/local-s3-upload",
                "file_key": "uploads/local_test_users.csv"
            }
            self.wfile.write(json.dumps(response_payload).encode('utf-8'))
            return

        return super().do_GET()

    def do_PUT(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == '/local-s3-upload':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            
            print("Received simulated S3 PUT upload.")
            count = ingest_csv_to_postgres(body)
            print(f"CSV ingestion complete: {count} users processed.")

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"message": "Upload & Ingestion Complete", "users": count}).encode('utf-8'))
            return

        self.send_response(404)
        self.end_headers()

if __name__ == "__main__":
    print(f"==================================================")
    print(f">> Smart Loan Matcher Local Dev Server")
    print(f">> Open: http://localhost:{PORT}")
    print(f">> Default stats & upload mock endpoints active")
    print(f"==================================================")
    with socketserver.TCPServer(("", PORT), LocalDemoHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
