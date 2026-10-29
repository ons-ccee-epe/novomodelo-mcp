"""Critério de go/no-go: regras sobre registros sintéticos, sem I/O."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from tests.e2e.go_no_go.criterio import Bloqueio, decidir, maioria_passou
from tests.e2e.go_no_go.estatistica import wilson
from tests.e2e.resultado.modelos import Conjunto, Estado, Registro


def reg(
    conjunto: Conjunto,
    caso: str,
    estado: Estado,
    repeticao: int = 1,
    agente: str = "ag",
    config: str = "padrao",
) -> Registro:
    if conjunto == "deterministica":
        agente, config = "-", "-"
    return Registro(
        rodada="r",
        conjunto=conjunto,
        caso=caso,
        agente=agente,
        config=config,
        repeticao=repeticao,
        estado=estado,
        motivo="",
        tools=(),
        duracao_s=0.0,
    )


def reps(conjunto: Conjunto, caso: str, estados: Sequence[Estado]) -> list[Registro]:
    return [reg(conjunto, caso, e, i + 1) for i, e in enumerate(estados)]


def test_wilson_valores_conhecidos():
    baixo, alto = wilson(8, 10)
    assert round(baixo, 3) == 0.490
    assert round(alto, 3) == 0.943
    assert wilson(0, 0) == (0.0, 1.0)


def test_wilson_extremos_ficam_em_zero_um():
    baixo, alto = wilson(10, 10)
    assert alto == pytest.approx(1.0)
    assert 0.0 < baixo < 1.0
    assert wilson(0, 10)[0] == pytest.approx(0.0)


def test_maioria_dois_de_tres_passa():
    assert maioria_passou(["passou", "passou", "falhou"])
    assert maioria_passou(["passou", "passou", "falhou", "erro_infra", "pulado"])


def test_maioria_um_de_tres_e_regressao():
    assert not maioria_passou(["passou", "falhou", "falhou"])
    base = reps("usuario", "c", ["passou", "passou", "passou"])
    alvo = reps("usuario", "c", ["passou", "falhou", "falhou"])
    d = decidir(alvo, base)
    assert d.veredito == "no-go"
    assert [b.regra for b in d.bloqueios] == ["regressao_maioria"]


def test_empate_nao_e_maioria():
    assert not maioria_passou(["passou", "falhou"])
    assert not maioria_passou([])


def test_deterministica_falha_bloqueia():
    alvo = [reg("deterministica", "d1", "falhou"), reg("deterministica", "d2", "passou")]
    d = decidir(alvo, None)
    assert d.veredito == "no-go"
    assert d.bloqueios == (
        Bloqueio(
            regra="deterministica",
            conjunto="deterministica",
            caso="d1",
            agente="-",
            evidencia=("execucoes/deterministica/d1/-/-/1",),
        ),
    )


def test_regressao_tool_bloqueia():
    base = [reg("tools", "t", "passou")]
    alvo = [reg("tools", "t", "falhou")]
    d = decidir(alvo, base)
    assert d.veredito == "no-go"
    assert d.bloqueios[0].regra == "regressao_tool"
    assert d.bloqueios[0].evidencia == ("execucoes/tools/t/ag/padrao/1",)


def test_tool_que_ja_falhava_na_base_nao_bloqueia():
    base = [reg("tools", "t", "falhou")]
    alvo = [reg("tools", "t", "falhou")]
    assert decidir(alvo, base).veredito == "go"


def test_um_cenario_isolado_que_oscila_nao_bloqueia():
    base = reps("usuario", "c", ["passou", "passou", "falhou"])
    alvo = reps("usuario", "c", ["passou", "falhou", "passou"])
    d = decidir(alvo, base)
    assert d.veredito == "go"
    assert d.bloqueios == ()


def test_usuario_empate_agora_nao_e_maioria_falhou():
    base = reps("usuario", "c", ["passou", "passou"])
    alvo = reps("usuario", "c", ["passou", "falhou"])
    assert decidir(alvo, base).veredito == "go"


def test_erro_infra_vira_inconclusivo_nunca_go():
    base = [reg("tools", "t", "passou")]
    alvo = [reg("tools", "t", "erro_infra")]
    d = decidir(alvo, base)
    assert d.veredito == "inconclusivo"
    assert d.inconclusivos == ("tools/t/ag",)
    assert d.bloqueios == ()


def test_erro_infra_que_nao_muda_o_resultado_nao_e_inconclusivo():
    base = reps("usuario", "c", ["passou", "passou", "passou"])
    alvo = reps("usuario", "c", ["passou", "passou", "passou", "erro_infra"])
    d = decidir(alvo, base)
    assert d.veredito == "go"
    assert d.inconclusivos == ()


def test_erro_infra_que_bloquearia_de_qualquer_jeito_e_bloqueio():
    base = reps("usuario", "c", ["passou", "passou", "passou"])
    alvo = reps("usuario", "c", ["falhou", "falhou", "falhou", "erro_infra"])
    d = decidir(alvo, base)
    assert d.veredito == "no-go"
    assert d.inconclusivos == ()
    assert [b.regra for b in d.bloqueios] == ["regressao_maioria"]
    assert len(d.bloqueios[0].evidencia) == 4


def test_usuario_com_erro_infra_decisivo_e_inconclusivo():
    base = reps("usuario", "c", ["passou", "passou", "passou"])
    alvo = reps("usuario", "c", ["passou", "falhou", "erro_infra"])
    d = decidir(alvo, base)
    assert d.veredito == "inconclusivo"
    assert d.inconclusivos == ("usuario/c/ag",)


def test_deterministica_com_erro_infra_e_inconclusiva():
    d = decidir([reg("deterministica", "d", "erro_infra")], None)
    assert d.veredito == "inconclusivo"
    assert d.inconclusivos == ("deterministica/d/-",)


def test_pulado_nao_conta():
    base = [reg("tools", "t", "passou")]
    alvo = [reg("tools", "t", "pulado")]
    d = decidir(alvo, base)
    assert d.veredito == "go"
    assert d.pulados == ("tools/t/ag",)
    assert d.bloqueios == ()


def test_caso_novo_sem_base_nao_bloqueia():
    base = [reg("tools", "antigo", "passou")]
    alvo = [reg("tools", "novo", "falhou"), reg("tools", "antigo", "passou")]
    d = decidir(alvo, base)
    assert d.veredito == "go"
    assert d.sem_base == ("tools/novo/ag",)


def test_sem_baseline_so_deterministica_bloqueia():
    alvo = [reg("tools", "t", "falhou"), reg("usuario", "c", "falhou")]
    assert decidir(alvo, None).veredito == "go"
    alvo.append(reg("deterministica", "d", "falhou"))
    d = decidir(alvo, None)
    assert d.veredito == "no-go"
    assert [b.regra for b in d.bloqueios] == ["deterministica"]


def test_no_go_tem_precedencia_sobre_inconclusivo():
    base = [reg("tools", "a", "passou"), reg("tools", "b", "passou")]
    alvo = [reg("tools", "a", "falhou"), reg("tools", "b", "erro_infra")]
    d = decidir(alvo, base)
    assert d.veredito == "no-go"
    assert d.inconclusivos == ("tools/b/ag",)


def test_agentes_sao_grupos_separados_e_saida_ordenada():
    base = [reg("tools", "t", "passou", agente=a) for a in ("b", "a")]
    alvo = [reg("tools", "t", "falhou", agente=a) for a in ("b", "a")]
    d = decidir(alvo, base)
    assert [b.agente for b in d.bloqueios] == ["a", "b"]


def test_evidencia_ordenada_com_barra_normal():
    base = reps("usuario", "c", ["passou"] * 3)
    alvo = reps("usuario", "c", ["falhou"] * 3)[::-1]
    ev = decidir(alvo, base).bloqueios[0].evidencia
    assert ev == tuple(f"execucoes/usuario/c/ag/padrao/{i}" for i in (1, 2, 3))
    assert all("\\" not in e for e in ev)
