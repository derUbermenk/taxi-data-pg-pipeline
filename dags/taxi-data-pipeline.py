from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import create_engine
import numpy as np

# Define default arguments
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Define the DAG
dag = DAG(
    'taxi_ingestion',
    default_args=default_args,
    description='A DAG to extract one week of data from a CSV file',
    schedule_interval='@weekly',  # Use @weekly for the schedule interval
    start_date=datetime(2021, 7, 1),
    end_date=datetime(2021,8,7),
    catchup=False,
)

# Define the Python function for data extraction
def extract_weekly_records(ti, **context):
    execution_date = context['logical_date']
    start_date = execution_date
    end_date = start_date + timedelta(days=7)

    start_date = np.datetime64(start_date)
    end_date = np.datetime64(end_date)


    # URL = "https://github.com/DataTalksClub/nyc-tlc-data/releases/download/yellow/yellow_tripdata_2021-07.csv.gz"
    local_file_path = "/data/yellow_tripdata_2021-07.csv.gz"

    taxi_dtypes = {
       'VendorID': pd.Int64Dtype(),
       'passenger_count': pd.Int64Dtype(), 
       'trip_distance': float, 
       'RatecodeID': pd.Int64Dtype(),
       'store_and_fwd_flag': str,
       'PULocationID': pd.Int64Dtype(), 
       'DOLocationID': pd.Int64Dtype(),
       'payment_type': pd.Int64Dtype(),
       'fare_amount': float,
       'extra': float,
       'mta_tax': float,
       'tip_amount': float,
       'tolls_amount': float,
       'improvement_surcharge': float,
       'total_amount': float,
       'congestion_surcharge': float
    }

    parse_dates = ['tpep_pickup_datetime', 'tpep_dropoff_datetime']

    try:
        # Read the gzip compressed CSV file from the local path
        df = pd.read_csv(local_file_path, sep=",", compression='gzip', dtype=taxi_dtypes, parse_dates=parse_dates)

    except FileNotFoundError:
        # Handle file not found issues
        raise RuntimeError(f"File not found: {local_file_path}")

    # Ensure the 'tpep_pickup_datetime' column exists
    if 'tpep_pickup_datetime' not in df.columns:
        raise KeyError("The file does not contain a 'tpep_pickup_datetime' column.")

    # Convert the 'tpep_pickup_datetime' column to datetime
    df['tpep_pickup_datetime'] = pd.to_datetime(df['tpep_pickup_datetime'])

    # Filter the DataFrame to get records from the last week
    mask = (df['tpep_pickup_datetime'] >= start_date) & (df['tpep_pickup_datetime'] < end_date)
    weekly_records = df.loc[mask]

    weekly_records = weekly_records[weekly_records['passenger_count'] > 0]

    # Remove any records where passenger count is 0

    # Output the result to a new CSV file
    output_filename = f"/tmp/{start_date}_weekly_records.csv"      
    weekly_records.to_csv(output_filename, index=False)

    ti.xcom_push(key="weekly_record_filepath", value=output_filename)

def save_weekly_records(ti):
    db_url = 'postgresql+psycopg2://taxi:taxi@taxi_db:5432/taxi'
    engine = create_engine(db_url)

    # Read the CSV file
    csv_file= ti.xcom_pull(key="weekly_record_filepath", task_ids="extract_weekly_records")
    df = pd.read_csv(csv_file)

    # Define the table name
    table_name = 'taxi_trips'

    # Insert the data into the SQL table
    df.to_sql(table_name, engine, if_exists='append', index=False)

    return

extract_trips = PythonOperator(
    task_id='extract_weekly_records',
    python_callable=extract_weekly_records,
    provide_context=True,
    dag=dag,
)

save_trips = PythonOperator(
    task_id = 'save_weekly_records',
    python_callable=save_weekly_records,
    provide_context=True,
    dag=dag,
)

extract_trips >> save_trips
