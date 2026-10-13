"""novomodelo-mcp — servidor MCP (fachada local) sobre as CLIs do Novomodelo e do novomodelo-bridge.

Este pacote NÃO contém regra de negócio do Novomodelo. Cada ferramenta envelopa um
subcomando de CLI já existente (`novomodelo-bridge … --json`, `novomodelo … --json`) e
repassa o resultado. Ver docs/ no projeto Novomodelo (arquitetura e especificação).
"""

__version__ = "0.1.0"
