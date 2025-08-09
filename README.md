# Bot Assistente Comercial no Telegram

## Motivações
Infelizmente, ainda é muito comum perder uma venda por não saber montar uma estratégia específica ou quando uma pergunta é feita e o vendedor não consegue obter rapidamente uma resposta do time.

Pensando nessa dor, desenvolvi este produto: uma IA no Telegram que não fornece respostas engessadas ou apenas binárias/condicionais.

Com este assistente, você pode:

- Montar estratégias de venda personalizadas
- Encontrar o melhor preço para vendedor e cliente
- Consultar prazos
- Saber tributos e comissionamento
- Ter tudo em um só lugar, funcionando 24 horas por dia, 7 dias por semana
- Entender melhor seu cliente


## Como funciona?
O código-fonte está disponível aqui → [bot_assistente.py](https://github.com/CarlosDouradoPGR/bot_assistente/blob/main/bot_assistente.py)

Ele utiliza a API do DeepSeek para fornecer respostas mais precisas e humanizadas.
O bot é integrado a um banco de dados PostgreSQL com a seguinte estrutura:

<p align="center"> <img width="1112" height="196" alt="Estrutura do banco" src="https://github.com/user-attachments/assets/4d70fd12-64dc-4037-b4a0-84b7e993e76b" /> </p>
Você também pode conferir a estrutura completa em SQL neste arquivo → [sql.txt](https://github.com/CarlosDouradoPGR/bot_assistente/blob/main/sql.txt)

- O banco de dados serve como ponte entre a empresa e a IA:
- Alimenta a IA com dados relevantes
- Permite respostas personalizadas e precisas para cada vendedor
## Quanto custa esse projeto?

- *Servidor (Railway)* → versão gratuita (sem custo no momento)
- *API DeepSeek* → atualmente ~8 USD investidos

## Como testar?
Você pode enviar uma mensagem pro bot atráves desse link:[💬 Converse com o bot no Telegram](https://t.me/CDAssit_bot)

## Tecnologias utilizadas

- Python
- PostgreSQL
- API DeepSeek
- Bot do Telegram
- Railway (deploy)

