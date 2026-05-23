import os
import asyncio
import threading
import subprocess
from flask import Flask, render_template, jsonify, send_from_directory
import logging
import queue
import time
import argparse
from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent, GiftEvent, LikeEvent, ConnectEvent


# Desativa os logs padrão de requisições do servidor Werkzeug (Flask)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)  # Só vai mostrar mensagens na tela se for um ERRO crítico

def parse_arguments():
    parser = argparse.ArgumentParser(description='App de leitura de mensagens e presentes de lives do tiktok')
    parser.add_argument('user', default='rivellinodomingo', help='Nome do usuario, que voce quer monitorar a live.')
    return parser.parse_args()

app = Flask(__name__)

# CONFIGURAÇÃO DO TIKTOK (Coloque o @ que você quer monitorar)
TIKTOK_USERNAME = parse_arguments().user
client = TikTokLiveClient(unique_id=TIKTOK_USERNAME)

AUDIO_FILE = "resultado.wav"

# Fila de eventos pendentes que a página web vai consumir e exibir na tela
fila_alertas = []

# Cria uma fila de mensagens segura para rodar entre Threads
fila_processamento_tts = queue.PriorityQueue()

# Dicionário global para controlar os combos ativos
# Estrutura: { "nome_usuario": {"presente": "Rose", "quantidade": 1, "ultimo_timestamp": 12345678} }
combos_ativos = {}

# Estrutura: { "nome_usuario": total_likes_na_live }
likes_por_usuario = {}

# Guarda os IDs das últimas 50 mensagens para evitar repetições do histórico inicial
historico_mensagens_recentes = []

# Tempo em segundos para esperar o combo terminar antes da IA falar
TEMPO_ESPERA_COMBO = 4.0

def monitorar_e_enviar_combo(usuario):
    """Aguarda o tempo de espera terminar para verificar se o combo fechou,
    e então envia um único agradecimento para a fila da IA."""
    time.sleep(TEMPO_ESPERA_COMBO)

    if usuario in combos_ativos:
        dados = combos_ativos[usuario]
        agora = time.time()

        # Se já se passaram X segundos desde o ÚLTIMO presente enviado por ele, o combo fechou!
        if agora - dados["ultimo_timestamp"] >= TEMPO_ESPERA_COMBO:
            # Remove do dicionário de ativos para poder aceitar novos combos no futuro
            combos_ativos.pop(usuario)

            # Monta a frase baseada na quantidade
            if dados["quantidade"] > 1:
                mensagem_alerta = f"Obrigado pelo combo de {dados['quantidade']} {dados['presente']}s, {usuario}!"
            else:
                mensagem_alerta = f"Obrigado pelo {dados['presente']}, {usuario}!"

            print(f"🎁 Combo Fechado! Enviando para a IA: {mensagem_alerta}")

            # Envia para a fila do Kokoro com Prioridade 1 (Máxima)
            fila_processamento_tts.put((1, mensagem_alerta))

            # Alerta o HTML imediatamente para piscar o visual na tela (opcional)
            fila_alertas.append({
                "tipo": "gift",
                "reproduzir": True,
                "mensagem": mensagem_alerta
            })

# --- EVENTOS DO TIKTOK ---
@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    print(f"\n=========================================")
    print(f"✅ CONEXÃO ESTABELECIDA COM SUCESSO!")
    print(f"🤖 Monitorando agora a live de: @{event.unique_id}")
    print(f"=========================================\n")

@client.on(LikeEvent)
async def on_like(event: LikeEvent):
    usuario = event.user.unique_id

    try:
        # Extrai o 'count' (quantidade de cliques do bloco atual) que você descobriu
        likes_enviados = int(event.count) if hasattr(event, 'count') else 1

        # Opcional: Se quiser capturar o total geral da live que você mencionou
        total_da_live = int(event.total) if hasattr(event, 'total') else 0
    except Exception:
        likes_enviados = 1
        total_da_live = 0

    # Inicializa o usuário no dicionário caso seja a primeira vez dele curtindo
    if usuario not in likes_por_usuario:
        likes_por_usuario[usuario] = 0

    # Guarda o valor antigo para sabermos quando ele cruzar a barreira dos 200
    total_antigo = likes_por_usuario[usuario]
    likes_por_usuario[usuario] += likes_enviados
    total_atual = likes_por_usuario[usuario]

    # Print discreto no terminal para você acompanhar os blocos chegando
    print(f"❤️ {usuario} enviou um bloco de +{likes_enviados} curtidas! (Total dele: {total_atual} | Total da Live: {total_da_live})")

    # Verifica se ele cruzou a barreira de mais uma centena dupla (200, 400, 600...)
    if (total_atual // 200) > (total_antigo // 200):
        marcador = (total_atual // 200) * 200

        mensagem_likes = f"{usuario} enviou mais de {marcador} curtidas!"
        print(f"❤️ Meta de Likes! {mensagem_likes}")

        # Envia para a fila visual do HTML para piscar o banner na tela da live
        fila_alertas.append({
            "tipo": "like",
            "reproduzir": True,
            "mensagem": mensagem_likes
        })

@client.on(CommentEvent)
async def on_comment(event: CommentEvent):
    usuario = event.user.unique_id
    mensagem = event.comment

    # Cria uma chave única baseada em quem falou e o que falou
    chave_mensagem = f"{usuario}:{mensagem}"

    # Se essa exata mensagem desse mesmo usuário acabou de ser recebida, ignora o reenvio
    if chave_mensagem in historico_mensagens_recentes:
        return

    # Adiciona ao histórico de controle
    historico_mensagens_recentes.append(chave_mensagem)
    # Mantém apenas as últimas 30 mensagens no histórico para não acumular memória
    if len(historico_mensagens_recentes) > 30:
        historico_mensagens_recentes.pop(0)

    print(f"[{usuario}]: {mensagem}")

    # Ignorar comandos ou mensagens excessivamente longas
    if len(mensagem) > 100 or mensagem.startswith("!"):
        return

    texto_para_ia = f"{usuario} disse: {mensagem}"

    # Envia para a fila de prioridades do seu PC (Prioridade 2 = Chat Normal)
    fila_processamento_tts.put((2, texto_para_ia))

@client.on(GiftEvent)
async def on_gift(event: GiftEvent):
    usuario = event.user.unique_id
    presente = event.gift.name

    # O TikTokLive costuma enviar a contagem acumulada no próprio evento (event.gift.combo_count)
    # Mas como alguns presentes de clique único não acumulam nativamente, nosso script gerencia de forma manual e segura:
    agora = time.time()

    if usuario in combos_ativos and combos_ativos[usuario]["presente"] == presente:
        # Se o usuário já estava em combo com esse mesmo presente, apenas incrementa e atualiza o tempo
        combos_ativos[usuario]["quantidade"] += 1
        combos_ativos[usuario]["ultimo_timestamp"] = agora
        print(f"➕ [+1 no Combo] {usuario} está combando {presente}! Total atual: {combos_ativos[usuario]['quantidade']}")
    else:
        # Se é o primeiro presente ou um presente diferente, inicia um novo monitoramento
        combos_ativos[usuario] = {
            "presente": presente,
            "quantidade": 1,
            "ultimo_timestamp": agora
        }
        print(f"🎁 [Novo Combo Iniciado] {usuario} enviou um {presente}.")

        # Dispara uma Thread temporária em background para esperar o combo terminar
        # sem congelar a recepção de novos presentes da live
        threading.Thread(target=monitorar_e_enviar_combo, args=(usuario,), daemon=True).start()


# --- CONFIGURAÇÃO DA THREAD DO TIKTOK ---
def rodar_tiktok():
    """Função rodada em uma thread separada para escutar o TikTok continuamente"""
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        print(f"🤖 Linha do TikTok ativada para: @{TIKTOK_USERNAME}")
        client.run()
    except Exception as e:
        print(f"Conexão do TikTok encerrada ou indisponível: {e}")

def processador_de_audio():
    while True:
        # Agora recebemos a prioridade e o texto da tupla
        prioridade, texto_para_ia = fila_processamento_tts.get()

        tempo_start = time.time()

        # Um aviso no terminal para você ver a prioridade funcionando
        status_prio = "⚡ PRESENTE" if prioridade == 1 else "💬 CHAT"
        print(f"⚙️ [{status_prio}] Processando áudio agora: '{texto_para_ia}'")

        try:
            # Executa o Kokoro passando o texto
            subprocess.run(['python3', 'testar_voz.py', texto_para_ia], check=True)

            # Alerta o HTML para tocar
            fila_alertas.append({"tipo": "tts", "reproduzir": True})
            print(f"✅ Áudio procesado em {time.time() - tempo_start} segundos... Enviado para o navegador!")

        except Exception as e:
            print(f"❌ Erro ao processar o áudio na Thread: {e}")

        fila_processamento_tts.task_done()

# --- ROTAS DO FLASK (INTERFACE WEB) ---

@app.route('/')
def index():
    # Renderiza automaticamente o arquivo 'templates/index.html'
    return render_template('index.html')

@app.route('/obter_alerta')
def obter_alerta():
    """A página web consulta essa rota a cada segundo procurando novas interações"""
    if fila_alertas:
        return jsonify(fila_alertas.pop(0)) # Remove e entrega o primeiro alerta da fila
    return jsonify({"reproduzir": False})

@app.route('/audio')
def obter_audio():
    return send_from_directory(os.getcwd(), AUDIO_FILE)

if __name__ == '__main__':
    # 1. Thread 1: Escuta o TikTok
    thread_tiktok = threading.Thread(target=rodar_tiktok, daemon=True)
    thread_tiktok.start()

    # 2. Thread 2: Processa o Kokoro de forma isolada (NOVO)
    thread_audio = threading.Thread(target=processador_de_audio, daemon=True)
    thread_audio.start()

    # 3. Inicia o Flask
    print("🚀 Servidor da Live iniciado em http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
