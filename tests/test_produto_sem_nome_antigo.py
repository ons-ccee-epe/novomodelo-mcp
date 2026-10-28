"""O código, os testes e o README do produto não citam o nome antigo.

É o mesmo critério do checador de nome do repositório de destino: o trecho, em
qualquer caixa, em qualquer arquivo de texto.
"""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# Codificado para que este arquivo não seja, ele mesmo, uma ocorrência.
ANTIGO = bytes.fromhex("636f627265").decode()


def _arquivos():
    yield RAIZ / "README.md"
    for base in ("src", "tests"):
        for path in sorted((RAIZ / base).rglob("*")):
            if path.is_file() and "_bundled" not in path.parts and "__pycache__" not in path.parts:
                yield path


def test_produto_sem_nome_antigo():
    achados = []
    for path in _arquivos():
        try:
            texto = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, linha in enumerate(texto.splitlines(), 1):
            if ANTIGO in linha.lower():
                achados.append(f"{path.relative_to(RAIZ)}:{n}: {linha.strip()[:100]}")
    assert not achados, "\n".join(achados)
