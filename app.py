import os
import asyncio
import threading
import subprocess
from flask import Flask, render_template, jsonify, send_from_directory
import logging
import queue
import time
import sys
import emoji
import re
import requests  # pip install requests
import signal
import betterproto
import argparse
from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent, GiftEvent, LikeEvent, ConnectEvent


# Desativa os logs padrão de requisições do servidor Werkzeug (Flask)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)  # Só vai mostrar mensagens na tela se for um ERRO crítico

def parse_arguments():
    parser = argparse.ArgumentParser(description='App de leitura de mensagens e presentes de lives do tiktok')
    # O nargs='?' diz ao Python que o argumento é opcional
    parser.add_argument('user', type=str, nargs='?', default='rivellinodomingo', help='Nome do usuario, que voce quer monitorar a live.')
    return parser.parse_args()

app = Flask(__name__)

# CONFIGURAÇÃO DO TIKTOK (Coloque o @ que você quer monitorar)
TIKTOK_USERNAME = parse_arguments().user
client = TikTokLiveClient(unique_id=TIKTOK_USERNAME)

# sys.exit(0)

AUDIO_FILE = "resultado.wav"

likes_meme = 200
caracters_nick = 20
caracters_coment = 500

# Lista de alertas com ID sequencial global.
# Clientes enviam seu ultimo_id e recebem apenas alertas mais novos.
# Nunca fazemos pop() — cada cliente lê independentemente.
fila_alertas = []          # lista de dicts com campo "id"
fila_alertas_contador = 0  # ID global crescente
# Mantém no máximo N alertas para não crescer indefinidamente
FILA_ALERTAS_MAX = 50

# Cria uma fila de mensagens segura para rodar entre Threads
fila_processamento_tts = queue.PriorityQueue()

# ADICIONE ESTA LINHA: Contador para garantir a ordem cronológica correta
contador_ordem_chegada = 0

# Dicionário global para controlar os combos ativos
# Estrutura: { "nome_usuario": {"presente": "Rose", "quantidade": 1, "ultimo_timestamp": 12345678} }
combos_ativos = {}

# Estrutura: { "nome_usuario": total_likes_na_live }
likes_por_usuario = {}

# Guarda os IDs das últimas 50 mensagens para evitar repetições do histórico inicial
historico_mensagens_recentes = []

# Tempo em segundos para esperar o combo terminar antes da IA falar
TEMPO_ESPERA_COMBO = 4.0

def get_nickname_from_raw(event) -> str:
    raw = event.to_pydict(casing=betterproto.Casing.SNAKE)
    raw_str = str(raw)  # converte tudo pra string

    # Procura nick_name ou nickName seguido do valor
    match = re.search(r"'nick(?:_?)name':\s*'([^']+)'", raw_str, re.IGNORECASE)
    if match:
        return match.group(1)
    return 'Desconhecido'

def get_avatar_url(event) -> str:
    """Extrai a primeira URL do avatar do usuário do evento."""
    try:
        user = event.user
        raw = user.to_pydict(casing=betterproto.Casing.SNAKE)
        urls = (
            raw.get('avatar_thumb', {}).get('m_urls') or
            raw.get('avatar_medium', {}).get('m_urls') or
            raw.get('avatar_larger', {}).get('m_urls') or
            []
        )
        # Prefere .webp; pega a primeira disponível
        for url in urls:
            if url:
                return url
        return ''
    except Exception:
        return ''


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
            push_alerta({
                "tipo": "gift",
                "reproduzir": True,
                "mensagem": mensagem_alerta
            })

def filtrar_texto_para_kokoro(texto_original):
    """
    Remove todos os emojis de um texto usando a biblioteca 'emoji'.
    Substitui cada emoji por uma string vazia ('').
    """
    texto_filtrado = emoji.replace_emoji(texto_original, replace='')
    return texto_filtrado.strip() # O .strip() remove espaços extras das pontas

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
    nickname = get_nickname_from_raw(event)[:caracters_nick]

    # print(vars(event.user))
    # try:
    #     raw = event.to_pydict(casing=betterproto.Casing.SNAKE)
    #     print("RAW KEYS:", raw)  # imprime o dicionário completo
    # except Exception as e:
    #     print("Erro ao ler user_info:", e)

    # print(f"Nome do usuario @{usuario}     |      Nickname({nickname}) -- Nick Cortado {nickname[:caracters_nick]}")

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
    # print(f"❤️ {usuario} enviou um bloco de +{likes_enviados} curtidas! (Total dele: {total_atual} | Total da Live: {total_da_live})")

    # Verifica se ele cruzou a barreira de mais uma centena dupla (200, 400, 600...)
    if (total_atual // likes_meme) > (total_antigo // likes_meme):
        marcador = (total_atual // likes_meme) * likes_meme

        mensagem_likes = f"{nickname} enviou mais de {marcador} curtidas!"
        print(f"❤️ Meta de Likes! {mensagem_likes}")

        # Envia para a fila visual do HTML para piscar o banner na tela da live
        push_alerta({
            "tipo": "like",
            "reproduzir": True,
            "mensagem": mensagem_likes
        })

@client.on(CommentEvent)
async def on_comment(event: CommentEvent):
    global contador_ordem_chegada # Avisa o Python para usar a variável global
    usuario = event.user.unique_id
    nickname = get_nickname_from_raw(event)[:caracters_nick]
    mensagem = event.comment

    # print(vars(event))

    print(f"[{nickname}][@{usuario}]: {mensagem}")

    # try:
    #     raw = event.to_pydict(casing=betterproto.Casing.SNAKE)
    #     print("RAW KEYS:", raw)  # imprime o dicionário completo
    # except Exception as e:
    #     print("Erro ao ler user_info:", e)
    # sys.exit(0)
    chave_mensagem = f"{usuario}:{mensagem}"
    if chave_mensagem in historico_mensagens_recentes:
        return

    historico_mensagens_recentes.append(chave_mensagem)
    if len(historico_mensagens_recentes) > 30:
        historico_mensagens_recentes.pop(0)

    if len(mensagem) > caracters_coment:
        mensagem = mensagem[:caracters_coment]

    texto_para_ia = f"{nickname} disse: {mensagem}"

    # INCREMENTA E ENVIAR COM O CONTADOR DE DESEMPATE
    contador_ordem_chegada += 1
    # A estrutura agora é: (Prioridade, Contador, Texto)
    fila_processamento_tts.put((2, contador_ordem_chegada, texto_para_ia))

@client.on(GiftEvent)
async def on_gift(event: GiftEvent):
    usuario = event.user.unique_id
    nickname = get_nickname_from_raw(event)[:caracters_nick]
    avatar_url = get_avatar_url(event)
    gift = event.gift

    if gift is None:
        return

    # Usando a lógica oficial do GitHub da API para filtrar combos finalizados ou presentes únicos
    # Se NÃO está mais combando (acabou o clique) e é um presente de combo (type == 1)
    if not event.streaking and gift.type == 1:
        total_presentes = event.repeat_count
        if total_presentes > 1:
            mensagem_alerta = f"Obrigado pelo combo de {total_presentes} {gift.name}s, {nickname}!"
        else:
            mensagem_alerta = f"Obrigado pelo {gift.name}, {nickname}!"

        processar_alerta_presente(mensagem_alerta, nickname, avatar_url)

    # Se for um presente que NÃO acumula combo (tipo uma rosa isolada ou presente caro de clique único)
    elif gift.type != 1:
        mensagem_alerta = f"Obrigado pelo {gift.name}, {nickname}!"
        processar_alerta_presente(mensagem_alerta, nickname, avatar_url)

def processar_alerta_presente(mensagem_alerta, nickname='', avatar_url=''):
    """Função auxiliar para centralizar os envios sem repetir código"""
    global contador_ordem_chegada
    print(f"🎁 Presente Confirmado! Enviando para a IA: {mensagem_alerta}")

    contador_ordem_chegada += 1
    # Envia para a fila do Kokoro com Prioridade 1 (Máxima)
    fila_processamento_tts.put((1, contador_ordem_chegada, mensagem_alerta))

    # print("Avatar url: ", avatar_url)

    # Alerta o HTML imediatamente — inclui nickname e avatar para a lista de doadores
    push_alerta({
        "tipo": "gift",
        "reproduzir": True,
        "mensagem": mensagem_alerta,
        "nickname": nickname,
        "avatar_url": avatar_url
    })

def push_alerta(alerta: dict):
    """Adiciona alerta à lista global com ID sequencial e limpa excesso."""
    global fila_alertas_contador
    fila_alertas_contador += 1
    alerta['id'] = fila_alertas_contador
    fila_alertas.append(alerta)
    # Remove alertas antigos se passar do limite
    if len(fila_alertas) > FILA_ALERTAS_MAX:
        fila_alertas.pop(0)

# --- CONFIGURAÇÃO DA THREAD DO TIKTOK ---
def rodar_tiktok():
    """Função rodada em uma thread separada para escutar o TikTok continuamente"""
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        print(f"🤖 Linha do TikTok ativada para: @{TIKTOK_USERNAME}")
        client.run(fetch_gift_info=True)
    except Exception as e:
        print(f"Conexão do TikTok encerrada ou indisponível: {e}")



def processador_de_audio():
    while True:
        # CORREÇÃO AQUI: Agora desempacota 3 variáveis (recebe o 'contador' no meio) e flitramos emojis
        prioridade, contador, texto_filt = fila_processamento_tts.get()
        texto_para_ia = filtrar_texto_para_kokoro(texto_filt)

        tempo_start = time.time()
        status_prio = "⚡ PRESENTE" if prioridade == 1 else "💬 CHAT"
        print(f"⚙️ [{status_prio}] Processando áudio agora: '{texto_para_ia}'")

        try:
            subprocess.run(['python3', 'testar_voz.py', texto_para_ia], check=True)
            push_alerta({"tipo": "tts", "reproduzir": True})
            print(f"✅ Áudio processado em {time.time() - tempo_start} segundos... Enviado para o navegador!\n")

        except subprocess.CalledProcessError:
            print("⚠️ Geração de áudio interrompida ou falhou.")
        except Exception as e:
            print(f"❌ Erro ao processar o áudio na Thread: {e}")
        finally:
            fila_processamento_tts.task_done()

# --- ROTAS DO FLASK (INTERFACE WEB) ---

@app.route('/')
def index():
    # Renderiza automaticamente o arquivo 'templates/index.html'
    return render_template('index.html')

@app.route('/sw.js')
def service_worker():
    return send_from_directory(os.getcwd(), 'sw.js',
                               mimetype='application/javascript')

@app.route('/obter_alerta')
def obter_alerta():
    """
    Broadcast por ID: cada cliente envia seu ultimo_id (padrão -1).
    O servidor devolve todos os alertas com id > ultimo_id.
    Nenhum alerta é removido — cada cliente lê independentemente.
    """
    from flask import request as freq
    try:
        ultimo_id = int(freq.args.get('ultimo_id', -1))
    except (ValueError, TypeError):
        ultimo_id = -1

    novos = [a for a in fila_alertas if a['id'] > ultimo_id]
    if novos:
        return jsonify({"alertas": novos, "reproduzir": True})
    return jsonify({"reproduzir": False})

@app.route('/audio')
def obter_audio():
    return send_from_directory(os.getcwd(), AUDIO_FILE)

@app.route('/radio-proxy')
def radio_proxy():
    from flask import request as flask_request, Response

    url_stream = flask_request.args.get('url', '').strip()
    if not url_stream:
        return "URL não fornecida", 400

    # Garante esquema e caminho /stream
    if not url_stream.startswith('http'):
        url_stream = 'http://' + url_stream
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url_stream)
    if parsed.path in ('', '/'):
        parsed = parsed._replace(path='/stream')
        url_stream = urlunparse(parsed)

    print(f"\n📻 [RADIO-PROXY] Conectando em: {url_stream}")

    try:
        resp = requests.get(
            url_stream,
            stream=True,
            timeout=10,
            headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'audio/aac, audio/*, */*',
                'Connection': 'keep-alive',
                'Icy-MetaData': '0',
            }
        )

        print(f"📻 [RADIO-PROXY] Status: {resp.status_code}")
        print(f"📻 [RADIO-PROXY] Content-Type recebido: {resp.headers.get('Content-Type')}")

        if resp.status_code != 200:
            return f"Stream retornou status {resp.status_code}", 502

        # WifiAudioStreaming serve AAC — força o content-type correto
        # para o browser aceitar como áudio (sem isso retorna text/html em alguns casos)
        content_type = resp.headers.get('Content-Type', '')
        if 'audio' not in content_type:
            content_type = 'audio/aac'
        print(f"📻 [RADIO-PROXY] Content-Type enviado ao browser: {content_type}")

        def gerar():
            try:
                for i, chunk in enumerate(resp.iter_content(chunk_size=8192)):
                    if chunk:
                        if i == 0:
                            print(f"📻 [RADIO-PROXY] Streaming iniciado! Primeiro chunk: {len(chunk)} bytes")
                        yield chunk
            except Exception as e:
                print(f"❌ [RADIO-PROXY] Erro no stream: {e}")

        return Response(gerar(), content_type=content_type)

    except requests.exceptions.ConnectionError as e:
        print(f"❌ [RADIO-PROXY] Erro de conexão: {e}")
        return f"Não foi possível conectar em {url_stream}", 502
    except requests.exceptions.Timeout:
        print(f"❌ [RADIO-PROXY] Timeout")
        return "Timeout ao conectar no stream", 502
    except Exception as e:
        print(f"❌ [RADIO-PROXY] Erro inesperado: {e}")
        return f"Erro: {e}", 502

def encerrar_sistema_graciosamente(sinal, frame):
    """Função chamada automaticamente ao apertar Ctrl+C no terminal ou Termux"""
    print("\n🛑 Encerramento seguro solicitado! Desconectando serviços...")

    # 1. Desconecta do TikTok de forma limpa se estiver conectado
    if client.connected:
        print("🔌 Desconectando da Live do TikTok...")
        # Como o disconnect é uma função assíncrona (async), rodamos com o loop correto
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(client.disconnect())
            else:
                loop.run_until_complete(client.disconnect())
        except Exception:
            pass

    # 2. Limpa as filas de alertas e TTS para interromper novos processamentos
    print("🧹 Limpando filas de processamento...")
    while not fila_processamento_tts.empty():
        try:
            fila_processamento_tts.get_nowait()
            fila_processamento_tts.task_done()
        except queue.Empty:
            break

    print("👋 Sistema finalizado com sucesso. Até a próxima live!")
    # Fecha o processo principal de forma limpa (código 0 significa sem erros)
    os._exit(0)

# Registra o gerenciador para capturar o Ctrl+C (SIGINT)
signal.signal(signal.SIGINT, encerrar_sistema_graciosamente)

if __name__ == '__main__':
    # 1. Thread 1: Escuta o TikTok
    thread_tiktok = threading.Thread(target=rodar_tiktok, daemon=True)
    thread_tiktok.start()

    # 2. Thread 2: Processa o Kokoro de forma isolada (NOVO)
    thread_audio = threading.Thread(target=processador_de_audio, daemon=True)
    thread_audio.start()

    # 3. Inicia o Flask
    print("🚀 Servidor da Live iniciado em http://localhost:5000")
    # app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    # Com ssl_context do pacote pip pyopenssl
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, ssl_context='adhoc')
