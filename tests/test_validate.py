"""Testes de validacao de entrada das tools de comparacao (pytest).

Cobrem as invariantes de :mod:`novomodelo_mcp.adapters.validate`:

* ``tolerance`` valida no intervalo ``(0.0, 1.0]`` (limites: 0.0 invalido,
  1.0 valido, > 1.0 invalido);
* token de ``format`` restrito ao conjunto aceito pela CLI;
* a validacao NAO invoca o novomodelo-bridge (barra antes do subprocesso).
"""
import pytest

from novomodelo_mcp.adapters.validate import (
    VALID_FORMATS,
    validate_compare_inputs,
    validate_fmt,
    validate_tolerance,
)


# --- tolerance: limites do intervalo (0.0, 1.0] ---------------------------- #

@pytest.mark.parametrize("value", [0.5, 1.0, 0.0001, 1])
def test_tolerance_valida_retorna_none(value):
    assert validate_tolerance(value) is None


@pytest.mark.parametrize("value", [0.0, -0.1, 1.0001, 2, 5.0])
def test_tolerance_fora_do_intervalo_retorna_erro(value):
    env = validate_tolerance(value)
    assert env is not None
    assert env["status"] == "error"
    assert env["exit_code"] == 2


def test_tolerance_none_e_valida():
    assert validate_tolerance(None) is None


def test_tolerance_bool_e_recusada():
    # bool e subtipo de int, mas nao e uma tolerancia valida.
    env = validate_tolerance(True)
    assert env is not None and env["status"] == "error"


@pytest.mark.parametrize("value", ["0.5", "meio", [], {}])
def test_tolerance_tipo_invalido_retorna_erro(value):
    env = validate_tolerance(value)
    assert env is not None and env["status"] == "error"


# --- format: token no conjunto permitido ----------------------------------- #

@pytest.mark.parametrize("fmt", sorted(VALID_FORMATS))
def test_fmt_valido_retorna_none(fmt):
    assert validate_fmt(fmt) is None


def test_fmt_none_e_valido():
    assert validate_fmt(None) is None


@pytest.mark.parametrize("fmt", ["xml", "yaml", "", "JSON", "html,csv"])
def test_fmt_invalido_retorna_erro(fmt):
    env = validate_fmt(fmt)
    assert env is not None
    assert env["status"] == "error"
    assert env["exit_code"] == 2
    # a mensagem lista os tokens validos, para orientar o agente.
    msg = " ".join(env["diagnostics"])
    for token in VALID_FORMATS:
        assert token in msg


# --- validacao combinada ---------------------------------------------------- #

def test_compare_inputs_validos_retorna_none():
    assert validate_compare_inputs(0.5, "json") is None
    assert validate_compare_inputs(None, None) is None


def test_compare_inputs_reporta_tolerance_antes_de_fmt():
    # tolerance invalida tem precedencia sobre fmt invalido.
    env = validate_compare_inputs(9.0, "xml")
    assert env is not None
    assert "tolerance" in " ".join(env["diagnostics"]).lower()


def test_compare_inputs_fmt_invalido_com_tolerance_valida():
    env = validate_compare_inputs(0.5, "xml")
    assert env is not None
    assert "format" in " ".join(env["diagnostics"]).lower()
