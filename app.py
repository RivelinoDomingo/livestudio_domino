import os
import asyncio
import threading
import subprocess
from flask import Flask, render_template, jsonify, send_from_directory
import logging
import queue
import time
import sys
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

# Fila de eventos pendentes que a página web vai consumir e exibir na tela
fila_alertas = []

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

def get_nickname(event) -> str:
    try:
        # Tenta acessar via user_info bruto antes do ExtendedUser quebrar
        user_info = event.user_info
        raw = user_info.to_pydict(casing=betterproto.Casing.SNAKE)
        return (
            raw.get('nick_name') or
            raw.get('nickname') or
            raw.get('unique_id') or
            'Desconhecido'
        )
    except Exception:
        return 'Desconhecido'

def get_unique_id(event) -> str:
    try:
        user_info = event.user_info
        raw = user_info.to_pydict(casing=betterproto.Casing.SNAKE)
        return raw.get('unique_id') or raw.get('username') or 'Desconhecido'
    except Exception:
        return 'Desconhecido'

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
    usuario = get_unique_id(event)
    nickname = get_nickname(event)[:caracters_nick]

    # print(vars(event.user))

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
        fila_alertas.append({
            "tipo": "like",
            "reproduzir": True,
            "mensagem": mensagem_likes
        })

@client.on(CommentEvent)
async def on_comment(event: CommentEvent):
    global contador_ordem_chegada # Avisa o Python para usar a variável global
    usuario = get_unique_id(event)
    nickname = get_nickname(event)[:caracters_nick]
    mensagem = event.comment

    chave_mensagem = f"{usuario}:{mensagem}"
    if chave_mensagem in historico_mensagens_recentes:
        return

    historico_mensagens_recentes.append(chave_mensagem)
    if len(historico_mensagens_recentes) > 30:
        historico_mensagens_recentes.pop(0)

    print(f"[{usuario}]: {mensagem}")

    if len(mensagem) > 1000 or mensagem.startswith("!"):
        return

    texto_para_ia = f"{nickname} disse: {mensagem}"

    # INCREMENTA E ENVIAR COM O CONTADOR DE DESEMPATE
    contador_ordem_chegada += 1
    # A estrutura agora é: (Prioridade, Contador, Texto)
    fila_processamento_tts.put((2, contador_ordem_chegada, texto_para_ia))

@client.on(GiftEvent)
async def on_gift(event: GiftEvent):
    usuario = get_unique_id(event)
    nickname = get_nickname(event)[:caracters_nick]
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

        # Envia apenas uma vez o alerta definitivo para o console, IA e HTML
        processar_alerta_presente(mensagem_alerta)

    # Se for um presente que NÃO acumula combo (tipo uma rosa isolada ou presente caro de clique único)
    elif gift.type != 1:
        mensagem_alerta = f"Obrigado pelo {gift.name}, {nickname}!"
        processar_alerta_presente(mensagem_alerta)

def processar_alerta_presente(mensagem_alerta):
    """Função auxiliar para centralizar os envios sem repetir código"""
    global contador_ordem_chegada
    print(f"🎁 Presente Confirmado! Enviando para a IA: {mensagem_alerta}")

    contador_ordem_chegada += 1
    # Envia para a fila do Kokoro com Prioridade 1 (Máxima)
    fila_processamento_tts.put((1, contador_ordem_chegada, mensagem_alerta))

    # Alerta o HTML imediatamente para piscar o visual na tela
    fila_alertas.append({
        "tipo": "gift",
        "reproduzir": True,
        "mensagem": mensagem_alerta
    })


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
        # CORREÇÃO AQUI: Agora desempacota 3 variáveis (recebe o 'contador' no meio)
        prioridade, contador, texto_para_ia = fila_processamento_tts.get()

        tempo_start = time.time()
        status_prio = "⚡ PRESENTE" if prioridade == 1 else "💬 CHAT"
        print(f"⚙️ [{status_prio}] Processando áudio agora: '{texto_para_ia}'")

        try:
            subprocess.run(['python3', 'testar_voz.py', texto_para_ia], check=True)
            fila_alertas.append({"tipo": "tts", "reproduzir": True})
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
    """A página web consulta essa rota a cada segundo procurando novas interações"""
    if fila_alertas:
        return jsonify(fila_alertas.pop(0)) # Remove e entrega o primeiro alerta da fila
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
