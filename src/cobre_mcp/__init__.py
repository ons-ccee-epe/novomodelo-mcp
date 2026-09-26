"""cobre-mcp — servidor MCP (fachada offline) sobre as CLIs do Cobre e do cobre-bridge.

Este pacote NÃO contém regra de negócio do Cobre. Cada ferramenta envelopa um
subcomando de CLI já existente (`cobre-bridge … --json`, `cobre … --json`) e
repassa o resultado. Ver docs/ no projeto Cobre (arquitetura e especificação).
"""

__version__ = "0.1.0"
