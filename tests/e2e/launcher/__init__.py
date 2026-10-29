"""Launcher de dev (FastAPI) para disparar os testes E2E das tools MCP pela UI.

Este pacote NAO e um backend de producao. E um launcher LOCAL de desenvolvimento,
rodado na maquina do dev, cujo unico papel e receber um clique do frontend e
disparar os testes. A logica de teste (validacao, persistencia) e reusada de
tests/e2e/queries/*; o disparo de agente passa pelo executor em container e, no
launcher, responde 409.

Fluxo:
    frontend (SPA) --HTTP--> launcher FastAPI --subprocess--> motor de carga (modo tools)
    frontend <--/data/*-- ResultStore (results/*.json, metrics/history.jsonl)
"""
