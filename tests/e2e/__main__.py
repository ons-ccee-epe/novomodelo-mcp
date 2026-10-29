"""Linha de comando da bateria: `python -m tests.e2e <subcomando>`."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import jsonschema

from novomodelo_mcp.adapters.versions import expected_version
from tests.e2e import rodada
from tests.e2e.config import avisos, carregar_config, verificar
from tests.e2e.executor.casos import CASOS_GRANDES, pasta_preparados, preparar_publicos, resolver
from tests.e2e.executor.container import SEGREDO_CLAUDE
from tests.e2e.executor.imagens import (
    CLIENTES,
    ConfigMCP,
    FalhaPreparo,
    aviso_do_bridge,
    construir,
    criar_segredo,
    ler_config_mcp,
    tag_imagem,
)
from tests.e2e.go_no_go.criterio import Decisao, com_incompleto, decidir
from tests.e2e.go_no_go.lancamentos import (
    LancamentosCorrompido,
    marcar_lancamento,
    ultimo_lancamento,
)
from tests.e2e.go_no_go.relatorio import escrever_relatorio
from tests.e2e.resultado.armazenamento import (
    NOME_DECISAO,
    PADRAO_NOME,
    gravar_decisao,
    ler_manifesto,
    ler_registros,
)
from tests.e2e.resultado.junit import escrever_junit
from tests.e2e.resultado.modelos import SCHEMA_VERSAO, Manifesto, Registro, VersaoDesconhecida

NOME_RELATORIO = "relatorio-go-no-go.md"
NOME_JUNIT = "junit.xml"
CODIGOS_DO_VEREDITO = {"go": 0, "no-go": 1, "inconclusivo": 2}
CODIGO_SEGREDO = rodada.CODIGO_SEGREDO
CODIGO_USO = 64
SUBCOMANDOS_DE_USO_64 = ("go-no-go", "marcar-lancamento")
LIMITE_FALTAS = 20
ITENS_DO_AGENTE = {"claude": "token_claude", "kiro": "volume_kiro"}


def _config_mcp(valor: str) -> ConfigMCP:
    try:
        return ler_config_mcp(valor)
    except ValueError as erro:
        raise argparse.ArgumentTypeError(str(erro)) from None


def _agentes(valor: str) -> list[str]:
    nomes = [n.strip() for n in valor.split(",") if n.strip()]
    desconhecidos = [n for n in nomes if n not in CLIENTES]
    if not nomes or desconhecidos:
        raise argparse.ArgumentTypeError(
            f"agentes válidos: {', '.join(CLIENTES)}; recebido: {valor!r}"
        )
    return list(dict.fromkeys(nomes))


def _conjuntos(valor: str) -> list[str]:
    nomes = [n.strip() for n in valor.split(",") if n.strip()]
    desconhecidos = [n for n in nomes if n not in rodada.CONJUNTOS_COM_AGENTE]
    if not nomes or desconhecidos:
        raise argparse.ArgumentTypeError(
            f"conjuntos válidos: {', '.join(rodada.CONJUNTOS_COM_AGENTE)}; recebido: {valor!r}"
        )
    return list(dict.fromkeys(nomes))


def _nao_negativo(valor: str) -> int:
    try:
        numero = int(valor)
    except ValueError:
        numero = -1
    if numero < 0:
        raise argparse.ArgumentTypeError(f"inteiro >= 0 esperado: {valor!r}")
    return numero


def _positivo(valor: str) -> int:
    numero = _nao_negativo(valor)
    if numero == 0:
        raise argparse.ArgumentTypeError(f"inteiro >= 1 esperado: {valor!r}")
    return numero


def _origem(valor: str) -> tuple[str, str]:
    nome, sep, texto = valor.partition("=")
    if not sep or not nome.strip() or not texto.strip():
        raise argparse.ArgumentTypeError(f"formato <config>=<texto>: {valor!r}")
    return nome.strip(), texto.strip()


def _uso_sai_64(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Faz o erro de uso do subparser sair com o código de recusa, e não com o 2 do argparse."""

    def erro(mensagem: str):
        parser.print_usage(sys.stderr)
        parser.exit(CODIGO_USO, f"{parser.prog}: erro: {mensagem}\n")

    parser.error = erro  # type: ignore[method-assign]
    return parser


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m tests.e2e", description=__doc__)
    sub = p.add_subparsers(dest="subcomando", required=True)
    sub.add_parser("verificar", help="confere motor, pastas, token e volume do Kiro")
    prep = sub.add_parser("preparar", help="constrói as imagens e cria o secret do token")
    prep.add_argument(
        "--mcp",
        nargs="+",
        required=True,
        type=_config_mcp,
        metavar="sem|WHEEL",
        help="'sem' ou o caminho de uma wheel do novomodelo-mcp; repita para várias",
    )
    prep.add_argument("--agentes", type=_agentes, default=list(CLIENTES), help="claude,kiro")
    rod = sub.add_parser(
        "rodar",
        help="determinística e conjuntos com agente; retomável",
        description=(
            "Retomável pelo --rodada: uma execução com registro gravado não roda de novo, "
            "e um caso pulado gravado não é reavaliado."
        ),
        epilog="códigos de saída do rodar (não são os do go-no-go): "
        + "; ".join(f"{c} {t}" for c, t in rodada.CODIGOS_DE_SAIDA.items()),
    )
    rod.add_argument("--rodada", metavar="ID", help="cria ou retoma esta rodada")
    rod.add_argument(
        "--mcp",
        nargs="+",
        required=True,
        type=_config_mcp,
        metavar="sem|WHEEL",
        help="'sem' ou o caminho de uma wheel do novomodelo-mcp; repita para várias",
    )
    rod.add_argument(
        "--origem-mcp",
        action="append",
        type=_origem,
        default=[],
        metavar="CONFIG=TEXTO",
        help="de onde veio a wheel da configuração (release, commit); repetível",
    )
    rod.add_argument(
        "--conjuntos",
        type=_conjuntos,
        default=list(rodada.CONJUNTOS_COM_AGENTE),
        help="tools,usuario",
    )
    rod.add_argument("--filtro", metavar="PADRÕES", help="ids de caso ou cenário, com vírgula")
    rod.add_argument("--agentes", type=_agentes, default=list(CLIENTES), help="claude,kiro")
    rod.add_argument("--repeticoes", type=_positivo, default=3)
    rod.add_argument("--completa", action="store_true", help="acrescenta a configuração sem MCP")
    rod.add_argument(
        "--max-execucoes",
        type=_nao_negativo,
        default=rodada.ORCAMENTO_PADRAO.max_execucoes,
        help="0 é sem limite",
    )
    rod.add_argument(
        "--max-minutos",
        type=_nao_negativo,
        default=rodada.ORCAMENTO_PADRAO.max_minutos,
        help="0 é sem limite",
    )
    rod.add_argument(
        "--esperar-limite",
        type=_positivo,
        metavar="MINUTOS",
        help="no limite de uso, espera e retoma sozinha em vez de sair com 4",
    )
    rod.add_argument("--paralelo-por-agente", type=_positivo, default=3)
    gng = sub.add_parser(
        "go-no-go",
        help="veredito de uma rodada, com relatório e JUnit",
        description=(
            f"Aplica o critério à rodada e grava {NOME_RELATORIO} e {NOME_JUNIT} na pasta dela. "
            "Base de comparação, na ordem: --baseline-config (na mesma rodada, ou na de "
            "--baseline quando as duas vêm juntas); --baseline (a configuração de mesmo nome "
            "do --alvo); o último lançamento marcado (a configuração dele, procurada primeiro "
            "nesta rodada); sem base, só a determinística bloqueia. Base cuja rodada está "
            'bloqueada por segredo é recusada com 64 ("base indisponível"). Só uma rodada '
            "completa decide: com execução do plano sem registro, na rodada ou na base, ou com o "
            f"último fim do {rodada.ARQUIVO_LOG} diferente de 0, o veredito é inconclusivo e o "
            "relatório lista o que falta. Antes de gravar, o gitleaks varre a pasta da rodada."
        ),
        epilog=_codigos_do_go_no_go(),
    )
    _uso_sai_64(gng)
    gng.add_argument("rodada", metavar="RODADA")
    gng.add_argument("--alvo", required=True, metavar="CONFIG", help="configuração avaliada")
    gng.add_argument("--baseline", metavar="RODADA", help="rodada da base")
    gng.add_argument(
        "--baseline-config", metavar="CONFIG", help="configuração da base (na rodada da base)"
    )
    marcar = sub.add_parser(
        "marcar-lancamento",
        help="torna uma configuração da rodada a base do próximo go/no-go",
        epilog=(
            "códigos de saída do marcar-lancamento: 0 marcado; 3 rodada bloqueada por segredo; "
            "64 recusa de uso (argumentos inválidos, rodada ou configuração inexistente, "
            "rodada em andamento ou incompleta, manifesto ou lancamentos.json ilegível)"
        ),
    )
    _uso_sai_64(marcar)
    marcar.add_argument("rodada", metavar="RODADA")
    marcar.add_argument("versao", metavar="VERSAO")
    marcar.add_argument("--config", required=True, metavar="CONFIG")
    return p


def _codigos_do_go_no_go() -> str:
    return (
        "códigos de saída do go-no-go (não são os do rodar): 0 go; 1 no-go; "
        "2 inconclusivo (inclui rodada incompleta); 3 segredo bloqueado na rodada ou varredura "
        "que não rodou; 64 recusa de uso (argumentos inválidos, rodada em andamento, "
        "rodada, alvo ou configuração inexistente, manifesto ilegível, --baseline igual à própria rodada sem "
        "--baseline-config, lançamento marcado cuja rodada ou configuração não existe mais)"
    )


def _verificar(cfg) -> int:
    problemas = verificar(cfg)
    for problema in problemas:
        print(f"problema [{problema.item}]: {problema.mensagem}")
    for aviso in avisos(cfg):
        print(f"aviso: {aviso}")
    if not problemas:
        print("ambiente pronto")
    return 1 if problemas else 0


def _preparar(cfg, configs: list[ConfigMCP], agentes: list[str]) -> int:
    relevantes = {"motor", "cache", *(ITENS_DO_AGENTE[a] for a in agentes)}
    problemas = [p for p in verificar(cfg) if p.item in relevantes]
    for problema in problemas:
        print(f"problema [{problema.item}]: {problema.mensagem}")
    if problemas:
        return 1
    versao = expected_version()
    if versao is None:
        print(
            "erro: pin do novomodelo-bridge ausente nos metadados do novomodelo-mcp",
            file=sys.stderr,
        )
        return 1
    try:
        if "claude" in agentes:
            criar_segredo(cfg)
            print(f"secret {SEGREDO_CLAUDE} criado a partir do arquivo de token", flush=True)
        for c in configs:
            if aviso := aviso_do_bridge(c):
                print(f"aviso: {aviso}", flush=True)
            for agente in agentes:
                versoes = construir(c, agente, cfg)
                linha = {"imagem": tag_imagem(c, agente), "versoes": versoes}
                print(json.dumps(linha, ensure_ascii=False), flush=True)
        primeira = tag_imagem(configs[0], agentes[0])
        preparados = preparar_publicos(versao, primeira, cfg)
        print(json.dumps({"casos_publicos": preparados}, ensure_ascii=False), flush=True)
        grandes = {
            nome: "disponivel" if resolver(nome, cfg, pasta_preparados(cfg)) else "ausente"
            for nome in sorted(CASOS_GRANDES)
        }
        print(json.dumps({"casos_grandes": grandes}, ensure_ascii=False), flush=True)
    except FalhaPreparo as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    return 0


def _configs_da_rodada(args) -> list[ConfigMCP]:
    configs = list(args.mcp)
    if args.completa:
        configs.append(ler_config_mcp("sem"))
    return list({c.nome: c for c in configs}.values())


def _rodar(cfg, args, parser: argparse.ArgumentParser) -> int:
    configs = _configs_da_rodada(args)
    com_wheel = {c.nome for c in configs if c.wheel is not None}
    origens = dict(args.origem_mcp)
    if desconhecidas := sorted(set(origens) - com_wheel):
        parser.error(f"--origem-mcp sem wheel correspondente: {', '.join(desconhecidas)}")
    relevantes = {
        "motor",
        "cache",
        "resultados",
        "casos",
        "cenarios_extra",
        *(ITENS_DO_AGENTE[a] for a in args.agentes),
    }
    if "usuario" in args.conjuntos:
        relevantes.add(ITENS_DO_AGENTE["claude"])
    problemas = [p for p in verificar(cfg) if p.item in relevantes]
    for problema in problemas:
        print(f"problema [{problema.item}]: {problema.mensagem}")
    if problemas:
        return 1
    try:
        pasta = rodada.rodar(
            args.rodada,
            configs,
            args.conjuntos,
            args.agentes,
            args.repeticoes,
            cfg,
            rodada.Orcamento(args.max_execucoes, args.max_minutos),
            args.paralelo_por_agente,
            filtro=args.filtro,
            completa=args.completa,
            origens=origens,
            esperar_limite_min=args.esperar_limite,
        )
    except rodada.RodadaInterrompida as erro:
        if erro.pasta is not None:
            print(f"rodada: {erro.pasta}", flush=True)
        print(f"erro: {erro}", file=sys.stderr)
        return erro.codigo
    print(f"rodada: {pasta}", flush=True)
    return 0


class _Recusa(Exception):
    codigo = CODIGO_USO


class _Bloqueada(_Recusa):
    codigo = CODIGO_SEGREDO


def _pasta_da_rodada(cfg, nome: str, alvo: bool = True) -> Path:
    if not re.search(PADRAO_NOME, nome):
        raise _Recusa(f"nome de rodada inválido: {nome!r}")
    pasta = cfg.resultados / nome
    if not (pasta / "manifesto.json").is_file():
        raise _Recusa(f"rodada {nome!r} não existe em {cfg.resultados.name}/")
    if (dono := rodada.trava_viva(pasta, rodada.pid_vivo)) is not None:
        quem = f"PID {dono}" if dono else "outro processo"
        raise _Recusa(f"rodada {nome!r} em andamento ({quem}); espere o fim do rodar")
    if (pasta / rodada.ARQUIVO_BLOQUEIO).exists():
        erro = _Bloqueada if alvo else _Recusa
        raise erro(
            f"rodada {nome!r} bloqueada por segredo ({rodada.ARQUIVO_BLOQUEIO}); "
            "sem relatório nem veredito"
        )
    return pasta


def _ler(pasta: Path) -> tuple[Manifesto, list[Registro]]:
    try:
        return ler_manifesto(pasta), ler_registros(pasta)
    except (OSError, ValueError, VersaoDesconhecida, jsonschema.ValidationError) as erro:
        detalhe = erro.message if isinstance(erro, jsonschema.ValidationError) else erro
        raise _Recusa(f"resultado ilegível em {pasta.name}: {detalhe}") from erro


def _config_no_manifesto(manifesto: Manifesto, config: str, flag: str) -> None:
    if config not in manifesto.configs:
        conhecidas = ", ".join(manifesto.configs)
        raise _Recusa(
            f"{flag} {config!r} não está no manifesto da rodada {manifesto.rodada!r} "
            f"(configurações: {conhecidas})"
        )


def _faltas(
    cfg, pasta: Path, manifesto: Manifesto, registros: list[Registro], config: str
) -> list[str]:
    """O que falta para a configuração estar completa na rodada: o último `fim` do log com
    código 0 e uma execução gravada para cada uma do plano do manifesto."""
    faltas = []
    fim = rodada.ultimo_fim(pasta)
    if fim is None:
        faltas.append(f"{rodada.ARQUIVO_LOG}: sem evento fim (rodada não terminou)")
    elif fim[0] != 0:
        faltas.append(f"{rodada.ARQUIVO_LOG}: fim com código {fim[0]} ({fim[1]})")
    try:
        plano = rodada.chaves_planejadas(manifesto, cfg)
    except (OSError, ValueError) as erro:
        return [*faltas, f"plano do manifesto ilegível: {type(erro).__name__}"]
    gravadas = {(r.conjunto, r.caso, r.agente, r.config, r.repeticao) for r in registros}
    faltam = sorted(c for c in plano - gravadas if c[3] == config)
    return faltas + ["/".join(map(str, c)) for c in faltam]


@dataclass(frozen=True)
class _Base:
    registros: list[Registro] | None = None
    rotulo: str | None = None
    faltas: tuple[str, ...] = ()


def _base_de_outra_rodada(cfg, nome: str, config: str) -> _Base:
    try:
        pasta = _pasta_da_rodada(cfg, nome, alvo=False)
        manifesto, registros = _ler(pasta)
        _config_no_manifesto(manifesto, config, "base")
    except _Recusa as erro:
        raise _Recusa(f"base indisponível: {erro}") from erro
    return _Base(
        [r for r in registros if r.config == config],
        f"{config} · rodada {nome}",
        tuple(_faltas(cfg, pasta, manifesto, registros, config)),
    )


def _base_da_rodada(
    cfg, pasta: Path, manifesto: Manifesto, registros: list[Registro], config: str, rotulo: str
) -> _Base:
    return _Base(
        [r for r in registros if r.config == config],
        rotulo,
        tuple(_faltas(cfg, pasta, manifesto, registros, config)),
    )


def _escolher_base(
    cfg, args, pasta: Path, manifesto: Manifesto, registros: list[Registro]
) -> _Base:
    """A base de comparação, na ordem de escolha do `--help`."""
    if args.baseline_config:
        if args.baseline and args.baseline != manifesto.rodada:
            return _base_de_outra_rodada(cfg, args.baseline, args.baseline_config)
        _config_no_manifesto(manifesto, args.baseline_config, "--baseline-config")
        rotulo = f"{args.baseline_config} · rodada {manifesto.rodada}"
        return _base_da_rodada(cfg, pasta, manifesto, registros, args.baseline_config, rotulo)
    if args.baseline:
        if args.baseline == manifesto.rodada:
            raise _Recusa("--baseline é a própria rodada; informe --baseline-config")
        return _base_de_outra_rodada(cfg, args.baseline, args.alvo)
    try:
        ultimo = ultimo_lancamento(cfg.resultados)
    except LancamentosCorrompido as erro:
        raise _Recusa(str(erro)) from erro
    if ultimo is None:
        return _Base()
    config, de_rodada = ultimo["config"], ultimo["rodada"]
    if config in manifesto.configs and config != args.alvo:
        rotulo = f"{config} · rodada {manifesto.rodada} (lançamento {ultimo['versao']})"
        return _base_da_rodada(cfg, pasta, manifesto, registros, config, rotulo)
    if de_rodada == manifesto.rodada and config == args.alvo:
        return _Base()
    base = _base_de_outra_rodada(cfg, de_rodada, config)
    return replace(base, rotulo=f"{base.rotulo} (lançamento {ultimo['versao']})")


def _atomico(destino: Path, escrever: Callable[[Path], object]) -> None:
    fd, nome = tempfile.mkstemp(dir=destino.parent, prefix=f".{destino.name}.", suffix=".tmp")
    os.close(fd)
    temporario = Path(nome)
    try:
        escrever(temporario)
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(temporario, 0o666 & ~umask)
        os.replace(temporario, destino)
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise


def _go_no_go(cfg, args) -> int:
    try:
        pasta = _pasta_da_rodada(cfg, args.rodada)
        manifesto, registros = _ler(pasta)
        _config_no_manifesto(manifesto, args.alvo, "--alvo")
        base = _escolher_base(cfg, args, pasta, manifesto, registros)
    except _Recusa as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return erro.codigo
    if rodada.gravar_bloqueio(pasta, rodada.varrer_segredos(pasta)):
        print(
            f"erro: varredura de segredos bloqueou a rodada: {rodada.ARQUIVO_BLOQUEIO}; "
            "sem relatório nem veredito",
            file=sys.stderr,
        )
        return CODIGO_SEGREDO
    alvo = [r for r in registros if r.config in (args.alvo, rodada.CONFIG_DETERMINISTICA)]
    faltas = _faltas(cfg, pasta, manifesto, registros, args.alvo)
    if not any(r.conjunto == "deterministica" for r in registros):
        faltas.append("deterministica: sem registro")
    faltas += [f"base: {f}" for f in base.faltas]
    decisao: Decisao = com_incompleto(decidir(alvo, base.registros), list(dict.fromkeys(faltas)))
    do_relatorio = alvo + [r for r in (base.registros or []) if r not in alvo]
    _atomico(
        pasta / NOME_RELATORIO,
        lambda tmp: escrever_relatorio(
            manifesto, do_relatorio, decisao, args.rodada, base.rotulo, tmp, config_alvo=args.alvo
        ),
    )
    _atomico(pasta / NOME_JUNIT, lambda tmp: escrever_junit(alvo, tmp))
    gravar_decisao(
        pasta,
        {"schema_versao": SCHEMA_VERSAO, "alvo": args.alvo, "base": base.rotulo, **asdict(decisao)},
    )
    print(f"veredito: {decisao.veredito}")
    print(f"relatório: {NOME_RELATORIO}")
    print(f"junit: {NOME_JUNIT}")
    print(f"decisão: {NOME_DECISAO}")
    return CODIGOS_DO_VEREDITO[decisao.veredito]


def _marcar_lancamento(cfg, args) -> int:
    try:
        pasta = _pasta_da_rodada(cfg, args.rodada)
        manifesto, registros = _ler(pasta)
        _config_no_manifesto(manifesto, args.config, "--config")
        if faltas := _faltas(cfg, pasta, manifesto, registros, args.config):
            resto = f"; e mais {len(faltas) - LIMITE_FALTAS}" if len(faltas) > LIMITE_FALTAS else ""
            raise _Recusa(
                f"rodada {args.rodada!r} incompleta para {args.config!r}: "
                + "; ".join(faltas[:LIMITE_FALTAS])
                + resto
            )
        marcar_lancamento(cfg.resultados, args.rodada, args.versao, args.config)
    except _Recusa as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return erro.codigo
    except LancamentosCorrompido as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return CODIGO_USO
    print(f"lançamento {args.versao}: {args.config} da rodada {args.rodada}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args, extras = parser.parse_known_args(argv)
    if extras:
        if args.subcomando in SUBCOMANDOS_DE_USO_64:
            print(
                f"{parser.prog}: erro: argumentos desconhecidos: {' '.join(extras)}",
                file=sys.stderr,
            )
            return CODIGO_USO
        parser.error(f"unrecognized arguments: {' '.join(extras)}")
    cfg = carregar_config(os.environ)
    if args.subcomando == "verificar":
        return _verificar(cfg)
    if args.subcomando == "rodar":
        return _rodar(cfg, args, parser)
    if args.subcomando == "go-no-go":
        return _go_no_go(cfg, args)
    if args.subcomando == "marcar-lancamento":
        return _marcar_lancamento(cfg, args)
    return _preparar(cfg, args.mcp, args.agentes)


if __name__ == "__main__":
    sys.exit(main())
