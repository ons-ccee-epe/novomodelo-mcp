"""Teste de carga do servidor MCP do novomodelo.

Abre N clientes concorrentes, cada um com o seu próprio processo do servidor
(stdio), e chama direto as tools somente leitura do mix, sem agente de IA.
Mede latência, vazão e erros por tool e ao longo do tempo.

Módulos:
    - stats: percentis, agregação por tool e série temporal
    - mix: catálogo de chamadas somente leitura e seleção do mix
    - client: cliente MCP stdio e classificação do resultado de cada chamada
    - engine: execução concorrente (pré-voo, aquecimento, métricas)
    - resources: CPU/RSS dos processos do servidor (opcional, via psutil)
    - store: persistência em results/load/
    - run: CLI (``python -m tests.e2e.load.run``)
"""
