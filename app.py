import subprocess
import os
from flask import Flask, render_template_string, request, jsonify, send_from_directory

app = Flask(__name__)

# Caminho para o arquivo de áudio gerado
AUDIO_FILE = "resultado.wav"

# Interface HTML minimalista e moderna integrada
HTML_PAGE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kokoro TTS Interface</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #121214;
            color: #e1e1e6;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .container {
            background-color: #202024;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            width: 90%;
            max-width: 500px;
            text-align: center;
        }
        h1 { color: #00b37e; margin-bottom: 20px; font-size: 24px; }
        textarea {
            width: 100%;
            height: 100px;
            background-color: #121214;
            border: 1px solid #29292e;
            border-radius: 5px;
            color: #fff;
            padding: 10px;
            box-sizing: border-box;
            resize: none;
            font-size: 16px;
        }
        textarea:focus { border-color: #00b37e; outline: none; }
        button {
            background-color: #00b37e;
            color: white;
            border: none;
            padding: 12px 20px;
            margin-top: 15px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            transition: background 0.2s;
            width: 100%;
        }
        button:hover { background-color: #00875f; }
        button:disabled { background-color: #4d4d4d; cursor: not-allowed; }
        .audio-controls {
            margin-top: 25px;
            padding-top: 20px;
            border-top: 1px solid #29292e;
        }
        .btn-play { background-color: #4834d4; }
        .btn-play:hover { background-color: #686de0; }
        #status { margin-top: 10px; color: #8d8d99; font-size: 14px; }
    </style>
</head>
<body>

<div class="container">
    <h1>Kokoro TTS</h1>
    <textarea id="texto" placeholder="Digite o texto que a IA deve falar..."></textarea>
    <button id="btnGerar" onclick="gerarAudio()">Gerar e Ouvir</button>
    <div id="status"></div>

    <div class="audio-controls">
        <button id="btnRepetir" class="btn-play" onclick="repetirAudio()" disabled>▶ Repetir Áudio Atual</button>
    </div>
</div>

<script>
    // Elemento de áudio global que guarda o arquivo na memória do navegador
    let audio = new Audio();

    async function gerarAudio() {
        const texto = document.getElementById('texto').value;
        const btnGerar = document.getElementById('btnGerar');
        const btnRepetir = document.getElementById('btnRepetir');
        const status = document.getElementById('status');

        if (!texto.trim()) {
            alert("Por favor, digite algum texto.");
            return;
        }

        btnGerar.disabled = true;
        status.innerText = "Processando voz com Kokoro v1.0...";

        try {
            const response = await fetch('/falar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `texto=${encodeURIComponent(texto)}`
            });
            
            const data = await response.json();
            
            if (data.sucesso) {
                status.innerText = "Áudio gerado com sucesso!";
                // Adiciona um timestamp (?t=...) para burlar o cache do navegador e forçar o som novo
                audio.src = "/audio?" + new Date().getTime();
                audio.play();
                btnRepetir.disabled = false;
            } else {
                status.innerText = "Erro: " + data.erro;
            }
        } catch (err) {
            status.innerText = "Erro ao se comunicar com o servidor.";
        } finally {
            btnGerar.disabled = false;
        }
    }

    function repetirAudio() {
        audio.play();
    }
</script>

</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/falar', methods=['POST'])
def falar():
    texto = request.form.get('texto', '')
    
    try:
        # Executa o seu arquivo testar_voz.py passando o texto recebido como argumento
        # Usamos o python3 do próprio ambiente virtual
        resultado = subprocess.run(
            ['python3', 'testar_voz.py', texto],
            capture_output=True, text=True, check=True
        )
        return jsonify({"sucesso": True})
    except subprocess.CalledProcessError as e:
        return jsonify({"sucesso": False, "erro": e.stderr or str(e)})

@app.route('/audio')
def obter_audio():
    # Serve o arquivo .wav gerado para que a página possa reproduzir
    return send_from_directory(os.getcwd(), AUDIO_FILE)

if __name__ == '__main__':
    # Roda o servidor localmente na porta 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
