import os
from dotenv import load_dotenv
import psycopg2
from psycopg2 import pool
from psycopg2.extras import DictCursor
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import requests
import json
import re
import asyncio
import nest_asyncio
from datetime import datetime

# Carrega variáveis de ambiente
load_dotenv()

# Configuração do PostgreSQL Connection Pool
postgres_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    host=os.getenv('DB_HOST'),
    database=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    port=os.getenv('DB_PORT')
)

# Configurações da API
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
TOKEN_TELEGRAM = os.getenv('TELEGRAM_TOKEN')

def get_db_connection():
    return postgres_pool.getconn()

def release_db_connection(conn):
    postgres_pool.putconn(conn)

def save_message(user_id, role, content, produto_id=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Atualiza usuário ou cria novo
            cursor.execute("""
                INSERT INTO users (user_id, first_name, username, last_interaction)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE 
                SET last_interaction = NOW(),
                    first_name = EXCLUDED.first_name,
                    username = EXCLUDED.username
                """, (user_id, "Nome", "username"))  # Substitua por dados reais
            
            # Salva a mensagem
            cursor.execute("""
                INSERT INTO messages (user_id, role, content, produto_id)
                VALUES (%s, %s, %s, %s)
                """, (user_id, role, content, produto_id))
        conn.commit()
    except Exception as e:
        print(f"Erro ao salvar mensagem: {e}")
    finally:
        release_db_connection(conn)

def get_user_history(user_id, limit=6):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute("""
                SELECT role, content, produto_id 
                FROM messages 
                WHERE user_id = %s 
                ORDER BY timestamp DESC 
                LIMIT %s
                """, (user_id, limit))
            history = [{"role": row['role'], "content": row['content']} for row in cursor.fetchall()]
            return history[::-1]  # Inverte para ordem cronológica
    except Exception as e:
        print(f"Erro ao buscar histórico: {e}")
        return []
    finally:
        release_db_connection(conn)

def buscar_produto(texto):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute("""
                SELECT id, produto, capacidade, preco_base, desconto_max,
                       ROUND(preco_base * (1 - desconto_max/100), 2) as preco_final
                FROM produtos
                WHERE LOWER(produto) LIKE %s
                ORDER BY produto
                LIMIT 5
                """, (f'%{texto.lower()}%',))
            return cursor.fetchall()
    except Exception as e:
        print(f"Erro ao buscar produto: {e}")
        return []
    finally:
        release_db_connection(conn)
		
def formatar_resposta_produto(produto):
    return f"""
*📦 {produto['produto']}* ({produto['capacidade']})
*💰 Preço base:* R$ {produto['preco_base']:.2f}
*🔻 Desconto máximo:* {produto['desconto_max']}%
*💵 Preço final:* R$ {produto['preco_final']:.2f}
"""

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    texto = update.message.text
    
    # Primeiro busca produtos
    produtos = buscar_produto(texto)
    if produtos:
        resposta = "*🔍 Produtos encontrados:*\n\n"
        resposta += "\n".join([formatar_resposta_produto(p) for p in produtos])
        save_message(user.id, "assistant", resposta)
        await update.message.reply_text(resposta, parse_mode='Markdown')
        return
    
    # Se não encontrar produtos, usa DeepSeek
    historico = get_user_history(user.id)
    mensagens = [
        {"role": "system", "content": "Você é um assistente comercial especializado em produtos de açaí."},
        *historico,
        {"role": "user", "content": texto}
    ]
    
    resposta = await get_deepseek_response(mensagens)
    save_message(user.id, "assistant", resposta)
    await update.message.reply_text(resposta, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    save_message(user.id, "system", "Início de conversa")
    
    keyboard = [
        [InlineKeyboardButton("📦 Ver Produtos", callback_data='listar_produtos')],
        [InlineKeyboardButton("💵 Promoções", callback_data='promocoes')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "*👋 Olá, eu sou o assistente da CD Company!*\n\n"
        "Posso te ajudar com:\n"
        "- Consulta de produtos e preços\n"
        "- Cálculo de descontos\n"
        "- Informações sobre pedidos",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
	
def formatar_para_markdown(texto):
    # Remove formatação potencialmente problemática
    escape_chars = '_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in texto)

async def get_deepseek_response(messages):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Erro DeepSeek: {e}")
        return "Desculpe, ocorreu um erro ao processar sua solicitação."
		
async def main():
    application = ApplicationBuilder().token(TOKEN_TELEGRAM).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    await application.run_polling()

if __name__ == '__main__':
    nest_asyncio.apply()
    asyncio.run(main())