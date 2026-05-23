import os
import asyncio
import threading
import subprocess
from flask import Flask, render_template, jsonify, send_from_directory
import logging
import queue
from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent, GiftEvent


# Desativa os logs padrão de requisições do servidor Werkzeug (Flask)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)  # Só vai mostrar mensagens na tela se for um ERRO crítico


app = Flask(__name__)

AUDIO_FILE = "resultado.wav"
# Fila de eventos pendentes que a página web vai consumir e exibir na tela
fila_alertas = []

# Cria uma fila de mensagens segura para rodar entre Threads
fila_processamento_tts = queue.Queue()

# CONFIGURAÇÃO DO TIKTOK (Coloque o @ que você quer monitorar)
TIKTOK_USERNAME = "tiagonoronha77"
client = TikTokLiveClient(unique_id=TIKTOK_USERNAME)

# --- EVENTOS DO TIKTOK ---

@client.on(CommentEvent)
async def on_comment(event: CommentEvent):
    usuario = event.user.unique_id
    mensagem = event.comment
    print(f"[{usuario}]: {mensagem}")

    # Ignorar comandos ou mensagens excessivamente longas
    if len(mensagem) > 100 or mensagem.startswith("!"):
        return

    texto_para_ia = f"{usuario} disse: {mensagem}"

    fila_processamento_tts.put(texto_para_ia)
    # fila_alertas.append({"tipo": "tts", "reproduzir": True})

    # try:
    #     # Aciona o seu testar_voz.py passando o argumento
    #     subprocess.run(['python3', 'testar_voz.py', texto_para_ia], check=True)
    #     # Notifica a fila que o áudio do Kokoro está pronto para o HTML tocar
    #     fila_alertas.append({"tipo": "tts", "reproduzir": True})
    # except Exception as e:
    #     print(f"Erro ao gerar voz do chat: {e}")

@client.on(GiftEvent)
async def on_gift(event: GiftEvent):
    usuario = event.user.unique_id
    presente = event.gift.name
    print(f"🎁 {usuario} enviou um {presente}!")

    # Exemplo de lógica personalizada de gatilho de mimos
    mensagem_alerta = f"Obrigado pelo {presente}, {usuario}!"
    fila_processamento_tts.put(mensagem_alerta)

    # Adiciona na fila para o HTML piscar o gif/vídeo na tela
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
        client.run()
    except Exception as e:
        print(f"Conexão do TikTok encerrada ou indisponível: {e}")

def processador_de_audio():
    """Esta função roda em uma Thread própria, isolada, pegando os textos
    da fila um por um e gerando o áudio no tempo dele, sem travar o TikTok."""
    while True:
        # Pega o próximo texto da fila (fica bloqueado esperando se estiver vazia)
        texto_para_ia = fila_processamento_tts.get()

        print(f"⚙️ Processando áudio agora: '{texto_para_ia}'")
        try:
            # Executa o Kokoro. O PC fraco vai demorar o tempo que precisar aqui...
            subprocess.run(['python3', 'testar_voz.py', texto_para_ia], check=True)

            # SÓ DEPOIS QUE GRAVOU COM SUCESSO: Avisa o HTML para dar o Play!
            fila_alertas.append({"tipo": "tts", "reproduzir": True})
            print(f"✅ Áudio pronto e enviado para o navegador!")

        except Exception as e:
            print(f"❌ Erro ao processar o áudio na Thread: {e}")

        # Informa que terminou aquela tarefa
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
