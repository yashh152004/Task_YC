import os
import json
import time
import boto3
from botocore.config import Config

# student note: initialize s3 client with region
s3_client = boto3.client('s3', config=Config(signature_version='s3v4'))

BUCKET_NAME = os.environ.get('UPLOAD_BUCKET', 'loan-user-uploads-bucket')

def lambda_handler(event, context):
    print("Generating presigned url for client upload...")
    
    try:
        # Generate a unique filename using timestamp
        timestamp = int(time.time())
        # fileName = "users_raw.csv"  # old hardcoded test name
        file_key = f"uploads/{timestamp}_users.csv"
        
        # generate presigned url for PUT request
        # valid for 5 minutes (300 seconds)
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': file_key,
                'ContentType': 'text/csv'
            },
            ExpiresIn=300
        )
        
        print(f"Generated upload URL for key: {file_key}")
        
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET"
            },
            "body": json.dumps({
                "upload_url": presigned_url,
                "file_key": file_key,
                "message": "Upload directly to this S3 URL using PUT method"
            })
        }
        
    except Exception as e:
        print(f"Error while generating presigned URL: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"error": str(e)})
        }
