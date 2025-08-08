# -*- coding: utf-8 -*-
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from datetime import datetime
import os
import asyncio
import psycopg2
import requests
import nest_asyncio
from psycopg2.extras import DictCursor

# Configuração inicial
nest_asyncio.apply()

# Variáveis de ambiente
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
TOKEN_TELEGRAM = os.environ.get('TELEGRAM_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')

# Função de conexão com o banco de dados
def db_connection():
    return psycopg2.connect(DATABASE_URL)

# Funções do banco de dados
def save_message(update: Update, role: str, content: str, produto_id=None):
    user = update.message.from_user
    conn = db_connection()
    try:
        with conn.cursor() as cursor:
            # Usa os dados reais do usuário do Telegram
            cursor.execute("""
                INSERT INTO users (user_id, first_name, username, last_interaction)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE 
                SET last_interaction = NOW(),
                    first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                    username = COALESCE(EXCLUDED.username, users.username)
            """, (user.id, user.first_name, user.username))
            
            cursor.execute("""
                INSERT INTO messages (user_id, role, content, produto_id)
                VALUES (%s, %s, %s, %s)
            """, (user.id, role, content, produto_id))
        conn.commit()
    except Exception as e:
        print(f"Erro ao salvar mensagem: {e}")
    finally:
        conn.close()

def get_user_history(user_id, limit=6):
    conn = db_connection()
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
        conn.close()

def buscar_produto(texto):
    conn = db_connection()
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
        conn.close()

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

