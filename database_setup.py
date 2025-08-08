import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        port=os.getenv('DB_PORT')
    )

def setup_database():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Criação das tabelas (igual ao SQL que te passei anteriormente)
            cursor.execute(open("migrations/001_initial.sql", "r").read())
        conn.commit()
        print("Banco de dados configurado com sucesso!")
    except Exception as e:
        print(f"Erro ao configurar banco de dados: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    setup_database()