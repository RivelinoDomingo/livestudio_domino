import soundfile as sf
import argparse
# Mudança sutil na importação para a versão v1.0
from kokoro_onnx import Kokoro

def parse_arguments():
    parser = argparse.ArgumentParser(description='Converte texo em voz')
    parser.add_argument('texto', help='Texto a ser falado.')
    return parser.parse_args()
    
texto = parse_arguments().texto    
    
print("Carregando o modelo Kokoro v1.0...")
onnx_file = "kokoro-v1.0.onnx"
voices_file = "voices-v1.0.bin"

# Instancia usando a nova classe 'Kokoro'
kokoro = Kokoro(onnx_file, voices_file)

# Texto que a IA vai falar
#texto = "Olá! Testando a inteligência artificial Kokoro diretamente do ambiente Termux no Android. O som ficou bom?"

print("Gerando o áudio...")
# Na v1.0, o método de criar mudou ligeiramente para facilitar o uso:
samples, sample_rate = kokoro.create(
    text=texto,
    voice="pm_santa",
    speed=0.9,
    lang="pt-br"
)

# Salva o resultado
nome_arquivo = "resultado.wav"
sf.write(nome_arquivo, samples, sample_rate)
print(f"Sucesso! Áudio gravado com sucesso em: {nome_arquivo}")

