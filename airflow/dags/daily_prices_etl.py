from __future__ import annotations

import csv
import datetime as dt
import os
import random

import pandas as pd
import psycopg2

from airflow import DAG
from airflow.operators.python import PythonOperator

DATA_DIR = "/opt/airflow/dags/data"
os.makedirs(DATA_DIR, exist_ok=True)
RAW_CSV = os.path.join(DATA_DIR, "prices_raw.csv")

PG_HOST = "db"
PG_DB = "tcsdb"
PG_USER = "tcs"
PG_PASS = "tcs"
PG_PORT = 5432


def generate_dummy_csv(**_):
    rows = []
    for i in range(5):
        rows.append(
            {
                "name": f"product_{i}",
                "price": round(random.uniform(10, 5000), 2),
            }
        )
    with open(RAW_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "price"])
        writer.writeheader()
        writer.writerows(rows)


def transform_with_pandas(**_):
    df = pd.read_csv(RAW_CSV)
    # Normalización simple: name en lowercase y limitar 2 decimales
    df["name"] = df["name"].str.lower().str.strip()
    df["price"] = df["price"].round(2)
    df.to_csv(RAW_CSV, index=False)


def load_to_postgres(**_):
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASS
    )
    conn.autocommit = True
    cur = conn.cursor()
    # Insertar en la tabla items (name, price)
    with open(RAW_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute(
                "INSERT INTO items (name, price) VALUES (%s, %s)",
                (row["name"], row["price"]),
            )
    cur.execute(
        """
        INSERT INTO items (name, price)
        VALUES (%s, %s)
        ON CONFLICT (name) DO UPDATE
            SET price = EXCLUDED.price
        """,
        (row["name"], row["price"]),
    )
    cur.close()
    conn.close()


default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": dt.timedelta(seconds=30),
}

with DAG(
    dag_id="daily_prices_etl",
    description="Demo ETL: genera CSV, transforma con pandas y carga en Postgres",
    start_date=dt.datetime(2025, 11, 7),
    schedule="@daily",
    catchup=False,
    default_args=default_args,
    tags=["demo", "etl"],
) as dag:
    t_generate = PythonOperator(
        task_id="generate_dummy_csv",
        python_callable=generate_dummy_csv,
    )
    t_transform = PythonOperator(
        task_id="transform_with_pandas",
        python_callable=transform_with_pandas,
    )
    t_load = PythonOperator(
        task_id="load_to_postgres",
        python_callable=load_to_postgres,
    )

    t_generate >> t_transform >> t_load
