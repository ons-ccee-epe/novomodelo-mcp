"""Launcher de dev (FastAPI) para disparar os testes E2E das tools MCP pela UI.

Este pacote NAO e um backend de producao. E um launcher LOCAL de desenvolvimento,
rodado na maquina do dev, cujo unico papel e receber um clique do frontend e
executar o provedor de IA (kiro-cli ou claude-cli) que roda o teste. A logica de
teste (execucao, validacao, persistencia) e 100% reusada de tests/e2e/queries/*:
o launcher nao reimplementa nada do runner.

Fluxo:
    frontend (SPA) --HTTP--> launcher FastAPI --subprocess--> kiro-cli / claude-cli
                                                                 |
                                                                 v
                                                      tool MCP novomodelo::*
    frontend <--/data/*-- ResultStore (results/*.json, metrics/history.jsonl)
"""

__all__ = ["app"]
