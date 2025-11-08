from __future__ import annotations

import csv
import datetime as dt
import os
import random

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

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
    df["name"] = df["name"].str.lower().str.strip()
    df["price"] = df["price"].round(2)
    # Reglas simples:
    df = df.dropna(subset=["name", "price"])
    df = df[df["price"].between(0.01, 1_000_000)]
    df.to_csv(RAW_CSV, index=False)


def load_to_postgres(**_):
    import csv

    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Leer todo el CSV una sola vez
    with open(RAW_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # -------- UPSERT batch en items --------
    upsert_sql = """
        INSERT INTO items (name, price)
        VALUES %s
        ON CONFLICT (name) DO UPDATE
            SET price = EXCLUDED.price
    """
    upsert_values = [(r["name"], r["price"]) for r in rows]
    execute_values(cur, upsert_sql, upsert_values)

    # -------- Historial (append-only) --------
    # Usamos template para incluir NOW() sin armar tuplas de timestamps en Python
    hist_sql = "INSERT INTO item_prices (item_name, price, run_ts) VALUES %s"
    hist_values = [(r["name"], r["price"]) for r in rows]
    execute_values(cur, hist_sql, hist_values, template="(%s, %s, NOW())")

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
