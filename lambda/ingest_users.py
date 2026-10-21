import os
import csv
import io
import json
import urllib.request
import boto3
import psycopg2

s3_client = boto3.client('s3')

# Database connection details from environment variables
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'loan_matcher_db')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres123')
N8N_WEBHOOK_URL = os.environ.get('N8N_WEBHOOK_URL', 'http://localhost:5678/webhook/new-users')

def get_db_connection():
    # connect to postgres
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn

def trigger_n8n_webhook(total_inserted):
    # notify n8n that new users were uploaded
    print(f"Triggering n8n matching workflow at: {N8N_WEBHOOK_URL}")
    payload = json.dumps({"status": "success", "total_inserted": total_inserted}).encode('utf-8')
    req = urllib.request.Request(
        N8N_WEBHOOK_URL,
        data=payload,
        headers={'Content-Type': 'application/json'}
    )
    try:
        response = urllib.request.urlopen(req, timeout=10)
        print("n8n responded with code:", response.getcode())
    except Exception as e:
        print("Could not call n8n webhook (maybe local n8n is sleeping):", str(e))

def insert_batch(cursor, batch):
    insert_query = """
        INSERT INTO users (email, monthly_income, credit_score, employment_status, age)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (email) DO NOTHING;
    """
    cursor.executemany(insert_query, batch)

def parse_csv_and_insert(file_content):
    print("Starting to parse CSV file content...")
    reader = csv.DictReader(io.StringIO(file_content))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    batch = []
    total_processed = 0
    batch_size = 100 # chunk size of 100 records
    
    for row in reader:
        # email = row['email'].lower() # test lowercase
        email = row['email'].strip()
        
        # check salary here
        monthly_income = float(row.get('monthly_income', 0))
        
        credit_score = int(row.get('credit_score', 0))
        employment_status = row.get('employment_status', 'Unknown').strip()
        age = int(row.get('age', 0))
        
        batch.append((email, monthly_income, credit_score, employment_status, age))
        total_processed += 1
        
        # When batch reaches 100, push to Postgres
        if len(batch) >= batch_size:
            print(f"Inserting batch of {len(batch)} users...")
            insert_batch(cursor, batch)
            conn.commit()
            batch = []
            
    # Insert any remaining records
    if len(batch) > 0:
        print(f"Inserting final batch of {len(batch)} users...")
        insert_batch(cursor, batch)
        conn.commit()
        
    cursor.close()
    conn.close()
    
    print(f"Finished inserting! Total records processed: {total_processed}")
    return total_processed

def lambda_handler(event, context):
    print("Received S3 event for user ingestion!")
    # print(json.dumps(event)) # debug event
    
    try:
        # Extract bucket and file key from S3 event
        record = event['Records'][0]
        bucket_name = record['s3']['bucket']['name']
        file_key = record['s3']['object']['key']
        
        print(f"Fetching s3://{bucket_name}/{file_key}")
        
        response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
        file_content = response['Body'].read().decode('utf-8')
        
        # Parse in batches and insert into RDS Postgres
        total_inserted = parse_csv_and_insert(file_content)
        
        # On success call n8n webhook to trigger Workflow B (Matching Engine)
        trigger_n8n_webhook(total_inserted)
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "User ingestion complete",
                "processed_count": total_inserted
            })
        }
        
    except Exception as e:
        print("Error during user ingestion:", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
