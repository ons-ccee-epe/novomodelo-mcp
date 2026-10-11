"""Snapshot embutido de documentação e schemas do Cobre.

Conteúdo versionado (vendored) para que as tools ``docs_*`` e ``schema_*``
funcionem offline no primeiro uso, sem clone, env var ou o binário ``cobre``.

Layout:
* ``docs/``    — páginas ``.md``/``.mdx`` (mesmo layout de ``cobre-docs``).
* ``schemas/`` — arquivos ``*.schema.json`` dos tipos de arquivo do deck.

Atualize este snapshot com ``python scripts/sync_bundled.py`` (ver o script
para as fontes suportadas). É intencional que seja um snapshot: garante builds
determinísticos e conteúdo alinhado à versão publicada do ``cobre-mcp``.
"""
