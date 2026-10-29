"""A checagem de termos proibidos acusa `arquivo:linha: padrão` e nunca o trecho."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "ci" / "check_termos_proibidos.py"

CAMINHO_PESSOAL = "/home/" + "maria/dados"
NOME_ANTIGO = bytes.fromhex("636f627265").decode()
CASO_SECRETO = "caso_secreto"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.org", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    raiz = tmp_path / "repo"
    raiz.mkdir()
    _git(raiz, "init", "-q")
    return raiz


def _commit(repo: Path, arquivos: dict[str, str], mensagem: str = "chore: ajuste") -> None:
    for nome, texto in arquivos.items():
        alvo = repo / nome
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(texto, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", mensagem)


def _rodar(repo: Path, *args: str, interno: Path | None = None, toml: Path | None = None):
    env = {k: v for k, v in os.environ.items() if k != "NOVOMODELO_TERMOS_INTERNOS"}
    if interno is not None:
        env["NOVOMODELO_TERMOS_INTERNOS"] = str(interno)
    comando = [sys.executable, str(SCRIPT), "--raiz", str(repo), *args]
    if toml is not None:
        comando += ["--toml", str(toml)]
    return subprocess.run(
        comando, capture_output=True, text=True, encoding="utf-8", env=env, check=False
    )


def test_padrao_generico_acusa_arquivo_e_linha(repo):
    _commit(repo, {"docs/guia.md": f"limpo\nveja {CAMINHO_PESSOAL} aqui\n"})
    res = _rodar(repo)
    assert res.returncode == 1
    assert "docs/guia.md:2: caminho de maquina" in res.stdout
    assert "maria" not in res.stdout + res.stderr


def test_nome_antigo_codificado_e_acusado(repo):
    _commit(repo, {"a.txt": f"usa o {NOME_ANTIGO.upper()} antigo\n"})
    res = _rodar(repo)
    assert res.returncode == 1
    assert "a.txt:1: nome antigo" in res.stdout
    assert NOME_ANTIGO not in (res.stdout + res.stderr).lower()


def test_lista_interna_por_variavel(repo, tmp_path):
    lista = tmp_path / "interno.txt"
    lista.write_text(f"# comentario\n\n{CASO_SECRETO}\n", encoding="utf-8")
    _commit(repo, {"notas.md": f"ok\nvimos o {CASO_SECRETO.upper()} ontem\n"})
    res = _rodar(repo, interno=lista)
    assert res.returncode == 1
    assert "notas.md:2: interno #3" in res.stdout
    assert CASO_SECRETO not in (res.stdout + res.stderr).lower()
    assert "ontem" not in res.stdout


def test_sem_lista_interna_so_genericos(repo):
    _commit(repo, {"notas.md": f"vimos o {CASO_SECRETO} ontem\n"})
    res = _rodar(repo)
    assert res.returncode == 0, res.stdout + res.stderr


def test_permitido_por_caminho(repo, tmp_path):
    _commit(
        repo,
        {"vendor/docs.md": f"{CAMINHO_PESSOAL}\n", "src/app.py": f"x = '{CAMINHO_PESSOAL}'\n"},
    )
    toml = tmp_path / "termos.toml"
    toml.write_text(
        '[[padroes]]\nnome = "caminho"\nregex = "/home/[a-z]"\n\n'
        '[permitidos]\n"vendor/" = "docs de terceiros"\n',
        encoding="utf-8",
    )
    res = _rodar(repo, toml=toml)
    assert res.returncode == 1
    assert "src/app.py:1: caminho" in res.stdout
    assert "vendor/" not in res.stdout


def test_credito_ons_ccee_epe_no_pyproject_passa(repo):
    _commit(
        repo,
        {
            "pyproject.toml": 'authors = [{ name = "Operador Nacional do Sistema Eletrico - ONS" }]\n',
            "tests/e2e/README.md": "Mantido por ONS, CCEE e EPE.\n",
        },
    )
    res = _rodar(repo)
    assert res.returncode == 0, res.stdout + res.stderr


def test_desde_olha_so_commits_novos(repo):
    _commit(repo, {"velho.md": f"{CAMINHO_PESSOAL}\n"}, mensagem="chore: base")
    _commit(repo, {"novo.md": "limpo\n"}, mensagem="chore: novo")
    ok = _rodar(repo, "--desde", "HEAD~1", "--mensagens")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    _commit(repo, {"outro.md": "x\n" + CAMINHO_PESSOAL + "\n"}, mensagem="chore: outro")
    ruim = _rodar(repo, "--desde", "HEAD~1")
    assert ruim.returncode == 1
    assert "outro.md:2: caminho de maquina" in ruim.stdout
    assert "velho.md" not in ruim.stdout
    historico = _rodar(repo, "--historico")
    assert "velho.md:1: caminho de maquina" in historico.stdout


def test_desde_acusa_mensagem_de_commit(repo):
    _commit(repo, {"a.md": "a\n"}, mensagem="chore: base")
    _commit(repo, {"b.md": "b\n"}, mensagem="docs: veja o " + "ons" + "tec interno")
    sem = _rodar(repo, "--desde", "HEAD~1")
    assert sem.returncode == 0
    com = _rodar(repo, "--desde", "HEAD~1", "--mensagens")
    assert com.returncode == 1
    assert "mensagem: " + "ons" + "tec" in com.stdout


def test_bateria_sem_marca_nem_referencia_de_spec(repo):
    _commit(
        repo,
        {
            "tests/e2e/painel.md": "Homologado pela ONS\n",
            "tests/e2e/outro.md": "ver Req 3.2 da spec\n",
            "README.md": "Mantido por ONS\n",
        },
    )
    res = _rodar(repo)
    assert res.returncode == 1
    assert "tests/e2e/painel.md:1: marca ONS" in res.stdout
    assert "tests/e2e/outro.md:1: referencia de spec" in res.stdout
    assert "README.md" not in res.stdout
