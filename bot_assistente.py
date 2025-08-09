# -*- coding: utf-8 -*-
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from datetime import datetime
from psycopg2.extras import DictCursor
import psycopg2
import os
import re
import requests
import nest_asyncio
import asyncio

# ===== CONFIGURAÇÕES INICIAIS =====
nest_asyncio.apply()

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
TOKEN_TELEGRAM = os.environ.get('TELEGRAM_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')

# ===== CONEXÃO BANCO DE DADOS =====
def db_connection():
    return psycopg2.connect(DATABASE_URL)

def save_message(update: Update, role: str, content: str, produto_id=None):
    """Salva mensagens no banco"""
    user = update.message.from_user
    conn = None
    try:
        conn = db_connection()
        with conn.cursor() as cursor:
            # Atualiza ou insere usuário
            cursor.execute("""
                INSERT INTO users (user_id, first_name, username, last_interaction)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE 
                SET last_interaction = NOW(),
                    first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                    username = COALESCE(EXCLUDED.username, users.username)
            """, (user.id, user.first_name, user.username or None))
            
            # Salva mensagem
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
    """Busca histórico do usuário"""
    try:
        with db_connection().cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute("""
                SELECT role, content 
                FROM messages 
                WHERE user_id = %s 
                ORDER BY timestamp DESC 
                LIMIT %s
            """, (user_id, limit))
            return [{"role": row['role'], "content": row['content']} for row in cursor.fetchall()][::-1]
    except Exception as e:
        print(f"Erro ao buscar histórico: {e}")
        return []

def buscar_produto(texto: str, incluir_moedas=False) -> list:
    """Busca produtos no banco"""
    try:
        with db_connection().cursor(cursor_factory=DictCursor) as cursor:
            if incluir_moedas:
                cursor.execute("""
                    SELECT id, sku, produto, capacidade, preco_base, desconto_max,
                           preco_dolar, preco_euro,
                           ROUND(preco_base * (1 - desconto_max/100), 2) as preco_final
                    FROM produtos
                    WHERE LOWER(produto) LIKE %s OR LOWER(sku) LIKE %s
                    ORDER BY produto LIMIT 5
                """, (f'%{texto.lower()}%', f'%{texto.lower()}%'))
            else:
                cursor.execute("""
                    SELECT id, produto, capacidade, preco_base, desconto_max,
                           ROUND(preco_base * (1 - desconto_max/100), 2) as preco_final
                    FROM produtos
                    WHERE LOWER(produto) LIKE %s
                    ORDER BY produto LIMIT 5
                """, (f'%{texto.lower()}%',))
            return cursor.fetchall()
    except Exception as e:
        print(f"⚠️ Erro ao buscar produto: {e}")
        return []

# ===== FORMATADORES =====
def limpar_formatacao(texto: str) -> str:
    """Remove ### e ajusta listas e espaçamentos"""
    # Substitui títulos ### e ##
    texto = re.sub(r"^#{2,3}\s*(.*)", r"🎯 *\1*", texto, flags=re.MULTILINE)
    
    # Troca listas numeradas 1. 2. 3. por emojis
    for i in range(1, 10):
        texto = re.sub(rf"^{i}\.\s", f"{i}️⃣ ", texto, flags=re.MULTILINE)
    
    # Remove excesso de linhas em branco
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    
    return texto.strip()

def validar_markdown(texto: str) -> bool:
    """Valida pares de * e _ no Markdown"""
    return isinstance(texto, str) and texto.count('*') % 2 == 0 and texto.count('_') % 2 == 0

def formatar_resposta_produto(produto: dict, moedas=False) -> str:
    """Formata produto para exibição"""
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
    return f"""
*📦 {produto['produto']}* ({produto['capacidade']})
*💰 Preço base:* R$ {produto['preco_base']:.2f}
*🔻 Desconto máximo:* {produto['desconto_max']}%
*💵 Preço final:* R$ {produto['preco_final']:.2f}
"""

# ===== HANDLERS =====
async def handle_moeda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.lower()
    match = re.search(r'(?:do|da|de)\s+([^\?]+)', texto)
    termo_busca = match.group(1).strip() if match else texto
    
    produtos = buscar_produto(termo_busca, incluir_moedas=True)
    if produtos:
        resposta = "*🔍 Resultados:*\n\n" + "\n".join([formatar_resposta_produto(p, moedas=True) for p in produtos])
        resposta = limpar_formatacao(resposta)
        save_message(update, "assistant", resposta)
        await update.message.reply_text(resposta, parse_mode='Markdown')
    else:
        await update.message.reply_text("Não encontrei este produto. Digite /produtos para ver a lista completa.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    texto = update.message.text.lower()

    # Consulta monetária
    if any(p in texto for p in ['dólar', 'dolar', 'euro', 'usd', 'eur']):
        await handle_moeda(update, context)
        return

    # Busca produto
    produtos = buscar_produto(texto)
    if produtos:
        resposta = "*🔍 Produtos encontrados:*\n\n" + "\n".join([formatar_resposta_produto(p) for p in produtos])
        resposta = limpar_formatacao(resposta)
        save_message(update, "assistant", resposta)
        await update.message.reply_text(resposta, parse_mode='Markdown')
        return
    
    # Consulta IA
    user = update.message.from_user
    save_message(update, "user", texto)
    historico = get_user_history(user.id)
    mensagens = [
        {"role": "system", "content": prompt_sistema},
        *historico,
        {"role": "user", "content": texto}
    ]
    
    resposta = await get_deepseek_response(mensagens)
    resposta = limpar_formatacao(resposta)
    save_message(update, "assistant", resposta)
    await update.message.reply_text(resposta, parse_mode='Markdown' if validar_markdown(resposta) else None)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📦 Ver Produtos", callback_data='listar_produtos')],
        [InlineKeyboardButton("💵 Promoções", callback_data='promocoes')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    mensagem = (
        "*👋 Olá, eu sou o assistente da CD Company!*\n\n"
        "Posso te ajudar com:\n"
        "- Consulta de produtos e preços\n"
        "- Cálculo de descontos\n"
        "- Informações sobre pedidos"
    )
    await update.message.reply_text(mensagem, reply_markup=reply_markup, parse_mode='Markdown')

# ===== INTEGRAÇÃO IA =====
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
        r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Erro DeepSeek: {e}")
        return "Desculpe, ocorreu um erro ao processar sua solicitação."

# ===== PROMPT DO SISTEMA =====
prompt_sistema = """
Você é um assistente Comeercial da CD Company especialista em análise de produtos e marketing para comercio de exportaçõa, a CD Company é uma empresa Brasileia que
exporta para o mundo todo, você está atendendo vendedores pelo telegram, você deve ajudar o time comercial a fechar vendas, passar informações sobre produtos,
montar uma estratégia de venda de acordo com o cliente que o vendedor informar.

REGRAS GERAIS:
1. **NUNCA** use "###", "##" ou qualquer sintaxe de título Markdown.
2. Use sempre negrito com asteriscos (*) para destacar pontos importantes.
3. Use emojis relevantes no início de seções para torná-las mais visuais e atrativas.
4. Respostas curtas, diretas, e em linguagem natural, mantendo tom consultivo e profissional.
5. Estruture sempre que possível em tópicos claros e numerados com emojis: 1️⃣, 2️⃣, 3️⃣...
6. Evite parágrafos longos; mantenha frases objetivas.

OBJETIVO:
- Ao receber informações de um produto, explicar claramente:
  🎯 Por que sugerir este produto
  💡 Benefícios principais
  📊 Potenciais resultados de vendas
  🔍 Dicas extras de uso ou anúncio

O QUE NÃO FAZER:
- Não usar títulos Markdown (###, ##).
- Não responder com código.
- Não criar listas com hífens simples; sempre usar emojis.
- Não repetir informações já dadas.

FORMATO DE RESPOSTA (sempre seguir):
🎯 *Por que sugerir este produto?*
Texto curto e objetivo.

💡 *Benefícios principais*
1️⃣ Benefício um
2️⃣ Benefício dois
3️⃣ Benefício três



📊 *Potenciais resultados*
Texto breve e realista.

🔍 *Dicas extras*
Texto breve.
"""

# ===== MAIN =====
async def main():
    app = ApplicationBuilder().token(TOKEN_TELEGRAM).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
