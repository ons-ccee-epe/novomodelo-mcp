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
        '[permitidos]\n"vendor/" = { padroes = ["caminho"], motivo = "docs de terceiros" }\n',
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


def test_permitido_para_um_padrao_ainda_acusa_outro(repo, tmp_path):
    _commit(repo, {"vendor/docs.md": f"{CAMINHO_PESSOAL}\nhot" + "site\n"})
    toml = tmp_path / "termos.toml"
    toml.write_text(
        '[[padroes]]\nnome = "caminho"\nregex = "/home/[a-z]"\n\n'
        '[[padroes]]\nnome = "outro"\nregex = "hot' + 'site"\n\n'
        '[permitidos]\n"vendor/" = { padroes = ["caminho"], motivo = "docs" }\n',
        encoding="utf-8",
    )
    res = _rodar(repo, toml=toml)
    assert res.returncode == 1
    assert "vendor/docs.md:2: outro" in res.stdout
    assert "vendor/docs.md:1" not in res.stdout


def test_permitido_nao_libera_lista_interna(repo, tmp_path):
    lista = tmp_path / "interno.txt"
    lista.write_text(CASO_SECRETO + "\n", encoding="utf-8")
    _commit(repo, {"vendor/a.md": CASO_SECRETO + "\n"})
    toml = tmp_path / "termos.toml"
    toml.write_text(
        '[[padroes]]\nnome = "x"\nregex = "zzz"\n\n'
        '[permitidos]\n"vendor/" = { padroes = ["interno #1"], motivo = "tentativa" }\n',
        encoding="utf-8",
    )
    res = _rodar(repo, interno=lista, toml=toml)
    assert res.returncode == 1
    assert "vendor/a.md:1: interno #1" in res.stdout


def test_lista_interna_configurada_e_ausente_sai_com_erro(repo, tmp_path):
    _commit(repo, {"a.md": "limpo\n"})
    ausente = tmp_path / "pasta-reservada" / "lista.txt"
    res = _rodar(repo, interno=ausente)
    assert res.returncode == 2
    saida = res.stdout + res.stderr
    assert "pasta-reservada" not in saida
    assert str(tmp_path) not in saida


def test_lista_interna_vazia_segue_so_com_genericos(repo):
    _commit(repo, {"a.md": "limpo\n"})
    env = {k: v for k, v in os.environ.items() if k != "NOVOMODELO_TERMOS_INTERNOS"}
    env["NOVOMODELO_TERMOS_INTERNOS"] = ""
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--raiz", str(repo)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert res.returncode == 0


def test_lista_interna_com_regex_invalida_nao_imprime_o_termo(repo, tmp_path):
    lista = tmp_path / "interno.txt"
    lista.write_text("# c\ntermo_reservado(\n", encoding="utf-8")
    _commit(repo, {"a.md": "limpo\n"})
    res = _rodar(repo, interno=lista)
    assert res.returncode == 2
    assert "termo_reservado" not in res.stdout + res.stderr
    assert "linha 2" in res.stderr


def test_linha_adicionada_que_comeca_com_mais_nao_vira_cabecalho(repo):
    _commit(repo, {"a.md": "base\n"}, mensagem="chore: base")
    _commit(repo, {"a.md": "base\n++ x\n+++ b/falso.md\n" + CAMINHO_PESSOAL + "\n"})
    res = _rodar(repo, "--desde", "HEAD~1")
    assert res.returncode == 1
    assert "a.md:4: caminho de maquina" in res.stdout
    assert "falso.md" not in res.stdout


def test_merge_so_acusa_o_que_foi_resolvido_no_merge(repo):
    _commit(repo, {"a.md": "base\n"}, mensagem="chore: base")
    _git(repo, "checkout", "-q", "-b", "lado")
    _commit(repo, {"b.md": CAMINHO_PESSOAL + "\n"}, mensagem="chore: lado")
    _git(repo, "checkout", "-q", "-")
    _commit(repo, {"c.md": "c\n"}, mensagem="chore: principal")
    _git(repo, "merge", "-q", "--no-ff", "-m", "chore: merge", "lado")
    merge = subprocess.run(
        ["git", "rev-parse", "--short=7", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    res = _rodar(repo, "--desde", "HEAD~1")
    assert res.stdout.count("b.md:1") == 1
    assert merge not in res.stdout


def test_arquivo_fora_de_utf8_ainda_e_checado(repo):
    alvo = repo / "latin.txt"
    alvo.write_bytes(b"caf\xe9\n" + CAMINHO_PESSOAL.encode() + b"\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: latin")
    res = _rodar(repo)
    assert res.returncode == 1
    assert "latin.txt:2: caminho de maquina" in res.stdout


def test_marca_ons_so_acusa_dentro_de_tests_e2e(repo):
    _commit(repo, {"docs/a.md": "feito pela ONS\n", "tests/e2e/a.md": "feito pela ONS\n"})
    res = _rodar(repo)
    assert "tests/e2e/a.md:1: marca ONS" in res.stdout
    assert "docs/a.md" not in res.stdout


TRES_PADROES = f"{NOME_ANTIGO}\nver Req 3.2\ncaminho .ki" + "ro/settings\n"
TOML_PADRAO = RAIZ / "scripts" / "ci" / "termos_proibidos.toml"


def _repo_com_tres_padroes(repo: Path) -> None:
    _commit(repo, {"tests/e2e/a.md": TRES_PADROES})


def test_historico_ignora_os_padroes_da_secao(repo):
    _repo_com_tres_padroes(repo)
    res = _rodar(repo, "--historico", "--mensagens")
    assert res.returncode == 0, res.stdout + res.stderr


def test_arvore_e_desde_continuam_acusando(repo):
    _commit(repo, {"base.md": "x\n"}, mensagem="chore: base")
    _repo_com_tres_padroes(repo)
    for args in ((), ("--desde", "HEAD~1")):
        res = _rodar(repo, *args)
        assert res.returncode == 1
        for nome in ("nome antigo", "referencia de spec", "diretorio kiro"):
            assert "tests/e2e/a.md" in res.stdout and nome in res.stdout, (args, nome)


def test_historico_nunca_ignora_a_lista_interna(repo, tmp_path):
    lista = tmp_path / "interno.txt"
    lista.write_text(CASO_SECRETO + "\n", encoding="utf-8")
    _commit(repo, {"a.md": TRES_PADROES + CASO_SECRETO + "\n"})
    res = _rodar(repo, "--historico", interno=lista)
    assert res.returncode == 1
    assert "a.md:4: interno #1" in res.stdout
    assert "nome antigo" not in res.stdout


def test_toml_nao_contem_literalmente_os_termos_da_receita():
    texto = TOML_PADRAO.read_text(encoding="utf-8").lower()
    for termo in ("ons" + "tec", "hots" + "ite"):
        assert termo not in texto
