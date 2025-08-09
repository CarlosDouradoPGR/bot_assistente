# -*- coding: utf-8 -*-
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from datetime import datetime
import os
import asyncio
import psycopg2
import requests
import nest_asyncio
import re
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

# Funções do banco de dados atualizadas
def save_message(update: Update, role: str, content: str, produto_id=None):
    user = update.message.from_user
    conn = None
    try:
        conn = db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO users (user_id, first_name, username, last_interaction)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE 
                SET last_interaction = NOW(),
                    first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                    username = COALESCE(EXCLUDED.username, users.username)
            """, (user.id, user.first_name, user.username or None))
            
            cursor.execute("""
                INSERT INTO messages (user_id, role, content, produto_id)
                VALUES (%s, %s, %s, %s)
            """, (user.id, role, content, produto_id))
        conn.commit()
    except Exception as e:
        print(f"⚠️ Erro ao salvar mensagem: {e}")
    finally:
        if conn:
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
            return history[::-1]
    except Exception as e:
        print(f"Erro ao buscar histórico: {e}")
        return []
    finally:
        conn.close()

def buscar_produto(texto: str, incluir_moedas=False) -> list:
    """Busca produtos no banco de dados"""
    conn = None
    try:
        conn = db_connection()
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            if incluir_moedas:
                cursor.execute("""
                    SELECT id, sku, produto, capacidade, preco_base, desconto_max,
                           preco_dolar, preco_euro,
                           ROUND(preco_base * (1 - desconto_max/100), 2) as preco_final
                    FROM produtos
                    WHERE LOWER(produto) LIKE %s OR LOWER(sku) LIKE %s
                    ORDER BY produto
                    LIMIT 5
                """, (f'%{texto.lower()}%', f'%{texto.lower()}%'))
            else:
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
        print(f"⚠️ Erro ao buscar produto: {e}")
        return []
    finally:
        if conn:
            conn.close()

def formatar_resposta_produto(produto: dict, moedas=False) -> str:
    """Formata os dados do produto para mensagem Markdown"""
    if moedas:
        return f"""
*📦 {produto['produto']}* ({produto['capacidade']}) - SKU: {produto['sku']}
*💵 Preço BRL:* R$ {produto['preco_base']:.2f}
*💰 Preço USD:* $ {produto['preco_dolar']:.2f}
*💶 Preço EUR:* € {produto['preco_euro']:.2f}
*🔻 Desconto máximo:* {produto['desconto_max']}%
*🎯 Preço final:*
- BRL: R$ {produto['preco_final']:.2f}
- USD: $ {produto['preco_dolar'] * (1 - produto['desconto_max']/100):.2f}
- EUR: € {produto['preco_euro'] * (1 - produto['desconto_max']/100):.2f}
"""
    else:
        return f"""
*📦 {produto['produto']}* ({produto['capacidade']})
*💰 Preço base:* R$ {produto['preco_base']:.2f}
*🔻 Desconto máximo:* {produto['desconto_max']}%
*💵 Preço final:* R$ {produto['preco_final']:.2f}
"""

async def handle_moeda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lida especificamente com consultas monetárias"""
    texto = update.message.text.lower()
    user = update.message.from_user
    
    # Extrai o termo de busca (produto)
    match = re.search(r'(?:do|da|de)\s+([^\?]+)', texto)
    termo_busca = match.group(1).strip() if match else texto
    
    produtos = buscar_produto(termo_busca, incluir_moedas=True)
    
    if produtos:
        resposta = "*🔍 Resultados:*\n\n"
        resposta += "\n".join([formatar_resposta_produto(p, moedas=True) for p in produtos])
        save_message(update, "assistant", resposta)
        await update.message.reply_text(resposta, parse_mode='Markdown')
    else:
        await update.message.reply_text("Não encontrei este produto. Digite /produtos para ver a lista completa.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    texto = update.message.text.lower()
    
    # Verifica se é consulta monetária
    if any(palavra in texto for palavra in ['dólar', 'dolar', 'euro', 'usd', 'eur']):
        await handle_moeda(update, context)
        return
    
    user = update.message.from_user
    
    try:
        # Consulta padrão de produtos
        produtos = buscar_produto(texto)
        if produtos:
            resposta = "*🔍 Produtos encontrados:*\n\n"
            resposta += "\n".join([formatar_resposta_produto(p) for p in produtos])
            save_message(update, "assistant", resposta)
            await update.message.reply_text(resposta, parse_mode='Markdown')
            return
        
        # Consulta ao DeepSeek
        save_message(update, "user", texto)
        historico = get_user_history(user.id)
        mensagens = [
            {"role": "system", "content": prompt_sistema},
            *historico,
            {"role": "user", "content": texto}
        ]
        
        resposta = await get_deepseek_response(mensagens)
        save_message(update, "assistant", resposta)
        
        if validar_markdown(resposta):
            await update.message.reply_text(resposta, parse_mode='Markdown')
        else:
            await update.message.reply_text(resposta)
            
    except Exception as e:
        print(f"⚠️ Erro no handle_message: {e}")
        await update.message.reply_text("❌ Ocorreu um erro ao processar sua mensagem. Tente novamente.")

# ... (mantenha o restante do código igual: start, get_deepseek_response, main, etc.)

# -*- coding: utf-8 -*-
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from datetime import datetime
import os
import asyncio
import psycopg2
import requests
import nest_asyncio
import re
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

# Funções do banco de dados atualizadas
def save_message(update: Update, role: str, content: str, produto_id=None):
    user = update.message.from_user
    conn = None
    try:
        conn = db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO users (user_id, first_name, username, last_interaction)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE 
                SET last_interaction = NOW(),
                    first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                    username = COALESCE(EXCLUDED.username, users.username)
            """, (user.id, user.first_name, user.username or None))
            
            cursor.execute("""
                INSERT INTO messages (user_id, role, content, produto_id)
                VALUES (%s, %s, %s, %s)
            """, (user.id, role, content, produto_id))
        conn.commit()
    except Exception as e:
        print(f"⚠️ Erro ao salvar mensagem: {e}")
    finally:
        if conn:
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
            return history[::-1]
    except Exception as e:
        print(f"Erro ao buscar histórico: {e}")
        return []
    finally:
        conn.close()

def buscar_produto(texto: str, incluir_moedas=False) -> list:
    """Busca produtos no banco de dados"""
    conn = None
    try:
        conn = db_connection()
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            if incluir_moedas:
                cursor.execute("""
                    SELECT id, sku, produto, capacidade, preco_base, desconto_max,
                           preco_dolar, preco_euro,
                           ROUND(preco_base * (1 - desconto_max/100), 2) as preco_final
                    FROM produtos
                    WHERE LOWER(produto) LIKE %s OR LOWER(sku) LIKE %s
                    ORDER BY produto
                    LIMIT 5
                """, (f'%{texto.lower()}%', f'%{texto.lower()}%'))
            else:
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
        print(f"⚠️ Erro ao buscar produto: {e}")
        return []
    finally:
        if conn:
            conn.close()

def formatar_resposta_produto(produto: dict, moedas=False) -> str:
    """Formata os dados do produto para mensagem Markdown"""
    if moedas:
        return f"""
*📦 {produto['produto']}* ({produto['capacidade']}) - SKU: {produto['sku']}
*💵 Preço BRL:* R$ {produto['preco_base']:.2f}
*💰 Preço USD:* $ {produto['preco_dolar']:.2f}
*💶 Preço EUR:* € {produto['preco_euro']:.2f}
*🔻 Desconto máximo:* {produto['desconto_max']}%
*🎯 Preço final:*
- BRL: R$ {produto['preco_final']:.2f}
- USD: $ {produto['preco_dolar'] * (1 - produto['desconto_max']/100):.2f}
- EUR: € {produto['preco_euro'] * (1 - produto['desconto_max']/100):.2f}
"""
    else:
        return f"""
*📦 {produto['produto']}* ({produto['capacidade']})
*💰 Preço base:* R$ {produto['preco_base']:.2f}
*🔻 Desconto máximo:* {produto['desconto_max']}%
*💵 Preço final:* R$ {produto['preco_final']:.2f}
"""

async def handle_moeda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lida especificamente com consultas monetárias"""
    texto = update.message.text.lower()
    user = update.message.from_user
    
    # Extrai o termo de busca (produto)
    match = re.search(r'(?:do|da|de)\s+([^\?]+)', texto)
    termo_busca = match.group(1).strip() if match else texto
    
    produtos = buscar_produto(termo_busca, incluir_moedas=True)
    
    if produtos:
        resposta = "*🔍 Resultados:*\n\n"
        resposta += "\n".join([formatar_resposta_produto(p, moedas=True) for p in produtos])
        save_message(update, "assistant", resposta)
        await update.message.reply_text(resposta, parse_mode='Markdown')
    else:
        await update.message.reply_text("Não encontrei este produto. Digite /produtos para ver a lista completa.")


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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    texto = update.message.text.lower()
    
    # Verifica se é consulta monetária
    if any(palavra in texto for palavra in ['dólar', 'dolar', 'euro', 'usd', 'eur']):
        await handle_moeda(update, context)
        return
    
    user = update.message.from_user
    
    try:
        # Consulta padrão de produtos
        produtos = buscar_produto(texto)
        if produtos:
            resposta = "*🔍 Produtos encontrados:*\n\n"
            resposta += "\n".join([formatar_resposta_produto(p) for p in produtos])
            save_message(update, "assistant", resposta)
            await update.message.reply_text(resposta, parse_mode='Markdown')
            return
        
        # Consulta ao DeepSeek
        save_message(update, "user", texto)
        historico = get_user_history(user.id)
        mensagens = [
            {"role": "system", "content": prompt_sistema},
            *historico,
            {"role": "user", "content": texto}
        ]
        
        resposta = await get_deepseek_response(mensagens)
        save_message(update, "assistant", resposta)
        
        if validar_markdown(resposta):
            await update.message.reply_text(resposta, parse_mode='Markdown')
        else:
            await update.message.reply_text(resposta)
            
    except Exception as e:
        print(f"⚠️ Erro no handle_message: {e}")
        await update.message.reply_text("❌ Ocorreu um erro ao processar sua mensagem. Tente novamente.")
        

prompt_sistema = """
Você é o *Assistente Comercial da CD Company*, especializado em produtos de açaí e frutas tropicais. 

**Instruções:**
1. Sempre responda de forma *clara* e *objetiva* 
2. Use formatação Markdown simples (*negrito* para ênfase)
3. Quando mencionar produtos, inclua:
   - Nome do produto (*📦*)
   - Preço base (*💰*) 
   - Desconto máximo (*🔻*)
4. Mantenha o tom *amigável* mas *profissional*

**Dicas de formatação:**
- `*texto*` para negrito
- Evite emojis excessivos
- Links: `[texto](URL)`

**Exemplo de resposta:**
*📦 Açaí Premium* (1KG)  
*💰 Preço base:* R$ 59,90  
*🔻 Desconto máximo:* 10%  
*💵 Preço final:* R$ 53,91

**Importante:** Se não souber a resposta, diga:  
*"Vou verificar e te retorno. Poderia me enviar mais detalhes?"*
"""




async def main():
    application = ApplicationBuilder().token(TOKEN_TELEGRAM).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    await application.run_polling()

if __name__ == '__main__':
    nest_asyncio.apply()
    asyncio.run(main())
