"""Máscara de segredos aplicada a tudo que o executor grava."""

from __future__ import annotations

from novomodelo_mcp_e2e.executor.mascara import MASCARA, mascarar


def test_mascara_token_ecoado_e_bearer():
    texto = (
        "env CLAUDE_CODE_OAUTH_TOKEN=falso0000falso00 sk-ant-oat01-xyz "
        "Authorization: Bearer abc.def"
    )
    saida = mascarar(texto, ["falso0000falso00"])
    for resto in ("falso0000falso00", "sk-ant-oat01-xyz", "abc.def"):
        assert resto not in saida


def test_segredo_literal_curto_demais_nao_e_trocado():
    assert mascarar("valor curto abc", ["abc"]) == "valor curto abc"


def test_chave_em_json_mantem_o_nome_e_troca_o_valor():
    saida = mascarar('{"api_key": "valorfalso0000000000"}')
    assert saida == '{"api_key": "' + MASCARA + '"}'
