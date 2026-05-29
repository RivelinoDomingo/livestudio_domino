import urllib.request
import os

def baixar_arquivo(url, nome_destino):
    print(f"Iniciando o download de: {nome_destino}")
    print("Isso pode demorar um pouco dependendo da sua internet...")
    try:
        # Abre a URL lidando com todos os redirecionamentos automaticamente
        for f in os.listdir():
            if (f == nome_destino):
                print(f"O arquivo [{nome_destino}] já está baixado nesse diretório.\n")
                return
        with urllib.request.urlopen(url) as response, open(nome_destino, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
        tamanho = os.path.getsize(nome_destino) / (1024 * 1024)
        print(f"✓ {nome_destino} baixado com sucesso! Tamanho: {tamanho:.2f} MB\n")
    except Exception as e:
        print(f"✗ Erro ao baixar {nome_destino}: {e}\n")

# Os links oficiais e sem travas que você encontrou no repositório!
url_modelo = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
url_modelo_int8 = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx"
url_vozes = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

# Executa os downloads
baixar_arquivo(url_modelo, "kokoro-v1.0.onnx")
baixar_arquivo(url_modelo_int8, "kokoro-v1.0.int8.onnx")
baixar_arquivo(url_vozes, "voices-v1.0.bin")
