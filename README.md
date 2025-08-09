# Bot Assistente Comercial no Telegram 

## Motivações
Não deveria ser mas é muito comum perder uma venda por não saber montar uma estratégia especifica ou quando é feita uma pergunta e o vendedor não consegue uma resposta rapida com o seu time.
olhando para essa dor, resolvi desenvolver esse produto, uma IA que funciona no telegram mas sem respostas travadas ou apenas repostas binarias ou condicionais, intgeragindo com essa Ia você poderá montar uma estratégia de venda,
conseguir achar o melhor preço par o vendedor e para o cliente, além de informações como prazo, tributo e comicionamento, tudo em um so lugar e 24 horas por semana

## Como funciona?
É um código que você pode conferir em [bot_assistente.py](https://github.com/CarlosDouradoPGR/bot_assistente/blob/main/bot_assistente.py) que utliza uma API do Deep Seek pra deixar as repostas mais precisas e humanizadas
o bot é alimentando com um banco de dados Postgress que possui essa estrutura 

<p align="center">
  <img width="1112" height="196" alt="image" src="https://github.com/user-attachments/assets/4d70fd12-64dc-4037-b4a0-84b7e993e76b" />
</p>

você pode conferir a estrutra em SQL nesse arquivo: [sql.txt](https://github.com/CarlosDouradoPGR/bot_assistente/blob/main/sql.txt)
O DB ajuda na conexão entre a empresa e a IA, todos os dados que são passados pro DB informam a IA e dessa forma ela consegue melhorar as repostas e passar as informações correta para o vendedor

## Quanto custa esse projeto?
Atualmente é necessário pagar o servidor na Railway e a API do deep seek, até o momento gastei por volta de 8 USD mas estou usando o versão gratuita do servidor.

## Como testar?
Você pode enviar uma mensagem pro bot atráves desse link:[💬 Converse com o bot no Telegram](https://t.me/CDAssit_bot)

