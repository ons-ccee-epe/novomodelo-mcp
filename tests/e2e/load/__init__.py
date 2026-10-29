"""Teste de carga do servidor MCP do novomodelo.

Modo tools: N sessões, cada uma com o seu próprio processo do servidor (stdio),
chamam direto as tools do mix, sem agente de IA. Modo agent: N sessões de agente
(kiro-cli ou claude) rodam em laço os casos do ``cases.yaml`` que podem rodar em
paralelo. Com tool ou caso que grava na seleção, cada sessão trabalha numa cópia própria
das fixtures. Mede latência, vazão e erros ao longo do tempo.

Módulos:
    - stats: percentis, agregação por tool e série temporal
    - mix: catálogo de chamadas (leves, que gravam, pesadas, barradas) e seleção do mix
    - sandbox: cópia das fixtures por sessão, pastas das sessões do modo tools e disco
    - client: cliente MCP stdio e classificação do resultado de cada chamada
    - engine: execução concorrente do modo tools (pré-voo, aquecimento, métricas)
    - agent_cases: casos do modo agent, seleção e exclusões
    - agent_session: pasta e config isolados de cada sessão de agente
    - agent_setup: pré-voo sem tokens e fábrica de sessões do modo agent
    - agent_engine: execução concorrente do modo agent
    - capacity: sessões simultâneas recomendadas para a máquina e a seleção
    - resources: CPU/RSS da árvore de processos (opcional, via psutil)
    - store: persistência em results/load/ (criada na primeira gravação)
    - run: CLI (``python -m tests.e2e.load.run``)
"""
