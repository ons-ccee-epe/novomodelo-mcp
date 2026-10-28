#!/usr/bin/env bash
# Confere que toda dependência do MCP tem wheel em cada alvo e versão do Python suportados.
#
# Quem instala resolve as dependências na hora, sem o uv.lock. Para cada alvo, compara a
# resolução normal com a resolução só com wheels (`--no-build`): se diferem, algum pacote
# seria compilado na máquina de quem instala. Não basta instalar com `--no-build`, porque
# o uv volta para uma versão antiga que tem wheel e esconde o problema.
#
# Uso: scripts/conferir_wheels.sh <requisito>   (ex.: o caminho do wheel do MCP)
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "uso: $0 <requisito>" >&2
    exit 2
fi

# As tags das wheels da novomodelo-python: a de Linux x86_64 exige glibc 2.34.
readonly ALVOS=(
    x86_64-manylinux_2_34
    aarch64-manylinux_2_28
    aarch64-apple-darwin
    x86_64-apple-darwin
    x86_64-pc-windows-msvc
)
readonly PYTHONS=(3.12 3.13 3.14)

requisito="$1"
req="$(mktemp)"
trap 'rm -f "$req"' EXIT
case "$requisito" in
    *.whl) echo "novomodelo-mcp @ file://$(cd "$(dirname "$requisito")" && pwd)/$(basename "$requisito")" >"$req" ;;
    *) echo "$requisito" >"$req" ;;
esac

falhou=0
for alvo in "${ALVOS[@]}"; do
    for py in "${PYTHONS[@]}"; do
        compilar=(uv pip compile -q --no-header --no-annotate --python-platform "$alvo" --python-version "$py" "$req")
        if ! normal="$("${compilar[@]}")"; then
            echo "$alvo, Python $py: sem solução"
            falhou=1
            continue
        fi
        so_wheels="$("${compilar[@]}" --no-build 2>/dev/null)" || so_wheels=""
        if [[ "$normal" != "$so_wheels" ]]; then
            echo "$alvo, Python $py: sem wheel para" \
                "$(comm -23 <(sort <<<"$normal") <(sort <<<"$so_wheels") | tr '\n' ' ')"
            falhou=1
        fi
    done
done

if [[ "$falhou" -eq 0 ]]; then
    echo "OK: toda dependência tem wheel em cada alvo e versão do Python."
fi
exit "$falhou"
