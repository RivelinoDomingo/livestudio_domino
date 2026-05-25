# 🎲 LiveStudio Dominó

Overlay interativo para lives de **dominó no TikTok**, rodando no próprio celular Android via Firefox. Lê eventos da live em tempo real (comentários, presentes, curtidas), gera voz com IA e exibe um placar alimentado pelo Firebase — tudo com a câmera do celular transmitindo a mesa de jogo.

---

## ✨ Funcionalidades

- 📷 **Overlay de câmera** — captura via browser, sem app externo, com a interface rotacionada para o celular ficar deitado na mesa
- 🎤 **TTS com IA local** — lê comentários e agradece presentes com voz sintetizada pelo modelo Kokoro (roda offline na máquina)
- 🎁 **Alertas de presentes** — banner com vídeo/meme e fila de prioridade: gifts interrompem likes, combos são agrupados
- ❤️ **Alertas de curtidas** — dispara a cada marco de curtidas configurável (padrão: 200)
- 📯 **Placar ao vivo** — busca dados do Firebase Firestore e exibe nome, pontos, raios e lambretas de até 4 jogadores
- 📻 **Rádio Web** — integração com o app [WiFi Audio Streaming](https://github.com/marcomorosi06/WiFiAudioStreaming-Android) para tocar músicas durante a live, com ducking automático nos alertas
- 🔇 **Ducking de áudio** — a música abaixa automaticamente durante TTS e alertas e volta sozinha ao terminar
- 📦 **Cache offline** — Service Worker cacheia os vídeos de alerta da pasta `/static` para carregamento instantâneo
- 🔒 **HTTPS local** — necessário para câmera e Service Worker funcionarem no Firefox via IP da rede local

---

## 🗂️ Estrutura do projeto

```
livestudio_domino/
├── app.py                  # Servidor Flask principal
├── testar_voz.py           # Gerador de áudio via Kokoro ONNX
├── baixar_pesos.py         # Script para baixar os modelos da IA
├── sw.js                   # Service Worker (cache de arquivos estáticos)
├── resultado.wav           # Áudio gerado pelo TTS (criado em tempo de execução)
├── kokoro-v1.0.onnx        # Modelo de voz (baixado via baixar_pesos.py)
├── voices-v1.0.bin         # Vozes do modelo (baixado via baixar_pesos.py)
├── templates/
│   └── index.html          # Overlay da live (câmera + placar + alertas)
└── static/
    ├── EH_Nois.mp4         # Vídeo/meme exibido nos alertas de presente
    ├── DInovo.mp4          # Vídeo/meme exibido nos alertas de curtida
    └── manifest.json       # Manifesto PWA
```

---

## ⚙️ Pré-requisitos

- Python 3.10+
- Firefox (recomendado; testado no Firefox e Firefox Nightly para Android)
- Android com o app **WiFi Audio Streaming** instalado (opcional, para a rádio)
- Conta no **Firebase** com um projeto Firestore para o placar (opcional)
- O streamer deve estar **ao vivo no TikTok** para a conexão funcionar

---

## 🚀 Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/livestudio-domino.git
cd livestudio-domino
```

### 2. Crie e ative um ambiente virtual

```bash
python3 -m venv venv
source venv/bin/activate       # Linux / macOS
# venv\Scripts\activate        # Windows
```

### 3. Instale as dependências Python

```bash
pip install flask TikTokLive kokoro-onnx soundfile requests pyopenssl betterproto
```

| Pacote | Função |
|---|---|
| `flask` | Servidor web e rotas da API |
| `TikTokLive` | Escuta eventos da live do TikTok em tempo real |
| `kokoro-onnx` | Síntese de voz (TTS) local com o modelo Kokoro v1.0 |
| `soundfile` | Salva o áudio gerado em `.wav` |
| `requests` | Proxy HTTP para o stream de áudio da rádio |
| `pyopenssl` | Gera certificado HTTPS autoassinado para o Flask |
| `betterproto` | Serialização Protobuf usada internamente pelo TikTokLive |

### 4. Baixe os modelos de voz da IA

```bash
python3 baixar_pesos.py
```

Isso vai baixar dois arquivos na raiz do projeto:
- `kokoro-v1.0.onnx` (~310 MB) — modelo de síntese
- `voices-v1.0.bin` (~25 MB) — banco de vozes

### 5. Adicione seus vídeos de alerta

Coloque na pasta `static/` os dois vídeos que serão exibidos nos banners:

```
static/EH_Nois.mp4    ← exibido quando alguém manda um presente
static/DInovo.mp4     ← exibido quando alguém atinge a meta de curtidas
```

---

## ▶️ Uso

### Iniciando o servidor

```bash
# Monitora o usuário padrão definido em app.py
python3 app.py

# Ou passa o @ que você quer monitorar como argumento
python3 app.py nome_do_usuario
```

O servidor inicia em `https://0.0.0.0:5000`. Você verá no terminal:

```
🚀 Servidor da Live iniciado em http://localhost:5000
🤖 Linha do TikTok ativada para: @nome_do_usuario
✅ CONEXÃO ESTABELECIDA COM SUCESSO!
🤖 Monitorando agora a live de: @nome_do_usuario
```

### Acessando o overlay no celular

1. Descubra o IP da sua máquina na rede local:
   ```bash
   ip a        # Linux
   ipconfig    # Windows
   ```
2. No Firefox do celular, acesse `https://192.168.1.X:5000`
3. Na primeira vez, o Firefox vai exibir um aviso de certificado não confiável — toque em **Avançado → Aceitar risco e continuar**
4. Conceda permissão de câmera quando solicitado
5. O overlay já estará funcionando com o celular deitado na mesa

> **Dica:** Para que câmera e Service Worker funcionem, o acesso **deve ser via HTTPS** (via IP na rede local) ou via `localhost`. O protocolo HTTP puro bloqueia essas APIs nos navegadores modernos.

---

## 🔧 Configurações

### Usuário do TikTok

No `app.py`, linha 25, o usuário padrão é definido em:

```python
parser.add_argument('user', ..., default='rivellinodomingo', ...)
```

Altere `rivellinodomingo` para o seu @ ou passe como argumento ao iniciar.

### Meta de curtidas para alerta

```python
likes_meme = 200   # Dispara alerta a cada 200 curtidas acumuladas por usuário
```

### Tamanho máximo do nickname exibido

```python
caracters_nick = 20  # Nicknames maiores que isso são cortados
```

### Tempo de espera para fechar combo de presentes

```python
TEMPO_ESPERA_COMBO = 4.0  # segundos sem novo presente = combo encerrado
```

### Voz do TTS

Em `testar_voz.py`, você pode trocar a voz e o idioma:

```python
samples, sample_rate = kokoro.create(
    text=texto,
    voice="pm_santa",   # troque pela voz desejada
    speed=0.9,
    lang="pt-br"
)
```

Vozes disponíveis podem ser listadas consultando o arquivo `voices-v1.0.bin` ou a [documentação do kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx).

### Placar (Firebase)

O placar busca dados em tempo real do Firestore. A URL está em `templates/index.html`:

```javascript
const url = "https://firestore.googleapis.com/v1/projects/SEU-PROJETO/databases/(default)/documents/hardware/display";
```

Substitua `SEU-PROJETO` pelo ID do seu projeto Firebase. O documento deve ter os campos:

| Campo | Tipo | Descrição |
|---|---|---|
| `nome1` … `nome4` | string | Nome do jogador |
| `jogador1` … `jogador4` | integer | Pontos (0–4 blocos) |
| `raios1` … `raios4` | integer | Contador de raios |
| `lambretas1` … `lambretas4` | integer | Contador de lambretas |

### Rádio Web (WiFi Audio Streaming)

1. Instale o app [WiFi Audio Streaming](https://github.com/marcomorosi06/WiFiAudioStreaming-Android) no Android
2. Nas configurações do app, ative **HTTP Web Stream** na porta `8080`
3. No overlay, toque em ⚙️ → **📻 Rádio Web**
4. Digite o endereço no formato `http://192.168.1.X:8080` e toque em **▶ Ligar**

O Flask faz proxy do stream HTTP para HTTPS automaticamente, contornando a restrição de mixed-content do browser. O áudio é codec AAC.

---

## 🏗️ Arquitetura

O sistema roda com **3 threads paralelas** mais o servidor Flask:

```
┌─────────────────────────────────────────────────────┐
│                      app.py                          │
│                                                      │
│  Thread 1: TikTokLive (asyncio)                      │
│  └─ Escuta comentários, presentes e curtidas         │
│     └─ Comentários → fila_tts (prioridade 2)         │
│     └─ Presentes  → fila_tts (prioridade 1)          │
│     └─ Likes      → fila_alertas (visual direto)     │
│                                                      │
│  Thread 2: Processador de Áudio                      │
│  └─ Consome fila_tts em ordem de prioridade          │
│     └─ Chama testar_voz.py (Kokoro) em subprocess    │
│     └─ Grava resultado.wav                           │
│     └─ Notifica fila_alertas → tipo: "tts"           │
│                                                      │
│  Thread 3: Flask (principal)                         │
│  └─ GET /           → overlay HTML                   │
│  └─ GET /obter_alerta → polling de eventos           │
│  └─ GET /audio      → serve resultado.wav            │
│  └─ GET /radio-proxy → proxy do stream AAC           │
│  └─ GET /sw.js      → Service Worker                 │
└─────────────────────────────────────────────────────┘

         ▲ polling 1s
         │
┌────────────────┐
│  Firefox       │
│  (overlay)     │
│                │
│  Câmera bruta  │
│  Placar Firebase│
│  Banner alertas│
│  Rádio Web     │
└────────────────┘
```

### Fila de alertas visuais (front-end)

O `index.html` tem sua própria fila de prioridade em JavaScript:

- **Gifts (prioridade 1):** interrompem likes em exibição imediatamente
- **Likes (prioridade 2):** aguardam na fila se um gift estiver tocando
- **Mesmo tipo chegando:** só atualiza o texto, sem reiniciar o vídeo
- **TTS:** roda em paralelo (só áudio), sem interferir no banner visual
- **Ducking:** a rádio abaixa para ~15% do volume durante qualquer alerta e volta automaticamente

---

## 📦 Dependências completas

```
flask
TikTokLive
kokoro-onnx
soundfile
requests
pyopenssl
betterproto
```

Gere o `requirements.txt` com:

```bash
pip freeze > requirements.txt
# E para instalar as dependências necessácias 
pip install -r requirements.txt
```

---

## 🛑 Encerrando

Pressione `Ctrl+C` no terminal. O sistema encerra graciosamente: desconecta do TikTok, limpa as filas e fecha o Flask sem deixar processos órfãos.

