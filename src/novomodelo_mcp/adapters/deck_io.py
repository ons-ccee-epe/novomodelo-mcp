"""Leitura e edição de arquivos de deck (JSON/Parquet) DENTRO do contrato de dados.

Garantias de "não quebrar o Novomodelo":
  - JSON: a edição é validada contra o JSON Schema oficial do tipo (quando
    disponível em NOVOMODELO_MCP_SCHEMAS_DIR); grava só se passar (ou com force=True).
  - Parquet: a edição preserva o schema (mesmas colunas e mesmos dtypes); se a
    edição mudaria coluna/dtype, aborta sem gravar.
  - Sempre faz backup (`<arquivo>.bak`) e escrita atômica (tmp + os.replace).

Dependências pesadas (polars, jsonschema) são importadas de forma preguiçosa,
para o módulo carregar mesmo sem elas instaladas.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

_MISSING = object()


# ── Caminho de campo (dotted + índices de lista): "a.b[0].c" ──────────────────

def _tokens(path: str) -> list[Any]:
    toks: list[Any] = []
    for seg in path.split("."):
        m = re.match(r"^([^\[\]]+)?((?:\[\d+\])*)$", seg)
        if not m:
            raise ValueError(f"segmento de caminho inválido: {seg!r}")
        name, idxs = m.group(1), m.group(2)
        if name:
            toks.append(name)
        for i in re.findall(r"\[(\d+)\]", idxs):
            toks.append(int(i))
    return toks


def get_by_path(obj: Any, path: str, default: Any = _MISSING) -> Any:
    cur = obj
    for t in _tokens(path):
        try:
            cur = cur[t]
        except (KeyError, IndexError, TypeError):
            if default is _MISSING:
                raise
            return default
    return cur


def set_by_path(obj: Any, path: str, value: Any) -> None:
    toks = _tokens(path)
    if not toks:
        raise ValueError("caminho vazio")
    cur = obj
    for t in toks[:-1]:
        cur = cur[t]
    cur[toks[-1]] = value


# ── Resolução e validação de schema ───────────────────────────────────────────

def resolve_schema(path: str, schemas_dir: str | None) -> str | None:
    """Acha o *.schema.json correspondente pelo nome do arquivo (stem)."""
    if not schemas_dir:
        return None
    stem = Path(path).stem  # 'hydros.json' -> 'hydros'
    cand = Path(schemas_dir) / f"{stem}.schema.json"
    return str(cand) if cand.exists() else None


def validate_json(obj: Any, schema_path: str | None) -> dict[str, Any]:
    """Valida `obj` contra o schema. jsonschema é opcional (import preguiçoso)."""
    if not schema_path:
        return {"validated": False, "errors": [],
                "note": "sem schema correspondente — validação por schema pulada"}
    try:
        from jsonschema.validators import validator_for
    except ImportError:
        return {"validated": False, "errors": [],
                "note": "jsonschema não instalado — validação por schema pulada"}
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    validator_cls = validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    errors = []
    for e in sorted(validator.iter_errors(obj), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in e.path) or "(raiz)"
        errors.append(f"{loc}: {e.message}")
    return {"validated": True, "errors": errors}


# ── Backup / restauração ──────────────────────────────────────────────────────

def backup_path(path: str) -> str:
    return f"{path}.bak"


def restore_backup(path: str) -> bool:
    bak = backup_path(path)
    if os.path.exists(bak):
        Path(path).write_bytes(Path(bak).read_bytes())
        return True
    return False


# ── JSON: leitura e edição ─────────────────────────────────────────────────────

def read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def edit_json(path: str, changes: list[dict], *, schemas_dir: str | None = None,
              dry_run: bool = False, force: bool = False) -> dict[str, Any]:
    """Aplica uma lista de mudanças [{path, value}] a um JSON de deck.

    Valida contra o schema (se houver) antes de gravar. Faz backup + escrita
    atômica. Nada é escrito em dry_run, ou quando há erro de schema sem force.
    """
    p = Path(path)
    if not p.exists():
        return {"status": "error", "diagnostics": [f"arquivo não existe: {path}"]}
    try:
        original = p.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {"status": "error", "diagnostics": [f"arquivo não está em UTF-8: {exc}"]}
    try:
        obj = json.loads(original)
    except json.JSONDecodeError as exc:
        return {"status": "error", "diagnostics": [f"JSON inválido: {exc}"]}

    applied = []
    for ch in changes:
        cpath = ch.get("path")
        if cpath is None:
            return {"status": "error",
                    "diagnostics": ["cada item de 'changes' precisa de 'path'"]}
        try:
            old = get_by_path(obj, cpath)
        except (KeyError, IndexError, TypeError, ValueError):
            old = _MISSING
        try:
            set_by_path(obj, cpath, ch.get("value"))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            return {"status": "error",
                    "diagnostics": [f"não foi possível aplicar '{cpath}': {exc}"]}
        applied.append({"path": cpath,
                        "old": None if old is _MISSING else old,
                        "new": ch.get("value")})

    schema = resolve_schema(path, schemas_dir)
    val = validate_json(obj, schema)
    schema_errors = val.get("errors", [])

    if schema_errors and not force:
        return {"status": "error", "written": False, "changes": applied,
                "schema": schema, "schema_errors": schema_errors,
                "diagnostics": ["edição violaria o schema — nada gravado "
                                "(use force=True para gravar mesmo assim)"]}

    if dry_run:
        return {"status": "ok", "written": False, "dry_run": True,
                "changes": applied, "schema": schema,
                "schema_errors": schema_errors, "note": val.get("note")}

    Path(backup_path(path)).write_text(original, encoding="utf-8")
    tmp = f"{path}.tmp"
    Path(tmp).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return {"status": "ok", "written": True, "changes": applied,
            "schema": schema, "schema_errors": schema_errors,
            "note": val.get("note"), "artifacts": {"backup": backup_path(path)}}


# ── Parquet: leitura e edição (import preguiçoso de polars) ────────────────────

def _pl():
    import polars as pl
    return pl


def _schema_map(df) -> dict[str, str]:
    return {name: str(dtype) for name, dtype in zip(df.columns, df.dtypes, strict=True)}


def read_parquet_summary(path: str, columns: list[str] | None = None,
                         limit: int = 50) -> dict[str, Any]:
    """Schema + contagem de linhas + amostra (nunca o arquivo inteiro)."""
    pl = _pl()
    lf = pl.scan_parquet(path)
    try:
        schema = lf.collect_schema()
        names = schema.names()
        dtypes = {n: str(schema[n]) for n in names}
    except AttributeError:  # polars antigo
        schema = lf.schema
        names = list(schema.keys())
        dtypes = {n: str(schema[n]) for n in names}
    nrows = lf.select(pl.len()).collect().item()
    sel = lf.select(columns) if columns else lf
    head = sel.head(limit).collect().to_dicts()
    return {"path": path, "columns": names, "dtypes": dtypes,
            "nrows": int(nrows), "head_rows": len(head), "head": head}


def describe_parquet(path: str) -> dict[str, Any]:
    pl = _pl()
    df = pl.read_parquet(path)
    return {"path": path, "nrows": df.height, "ncols": df.width,
            "dtypes": _schema_map(df), "describe": df.describe().to_dicts()}


def edit_parquet(path: str, where: dict, set_values: dict, *,
                 dry_run: bool = False) -> dict[str, Any]:
    """Edita células de um Parquet PRESERVANDO o schema.

    `where`: casamento por igualdade {coluna: valor} que seleciona as linhas.
    `set_values`: {coluna: novo_valor} aplicado às linhas selecionadas.
    Aborta sem gravar se alguma coluna não existir ou se a edição mudaria o
    schema (colunas/dtypes) — é essa a "trava de contrato" do Parquet.
    """
    if not set_values:
        return {"status": "error", "diagnostics": ["'set_values' vazio"]}
    pl = _pl()
    df = pl.read_parquet(path)
    before = _schema_map(df)

    for col in list(where) + list(set_values):
        if col not in df.columns:
            return {"status": "error",
                    "diagnostics": [f"coluna inexistente: {col}",
                                    f"colunas: {df.columns}"]}

    mask = pl.lit(True)
    for col, val in where.items():
        mask = mask & (pl.col(col) == val)
    n_match = df.filter(mask).height

    exprs = [pl.when(mask).then(pl.lit(val)).otherwise(pl.col(col)).alias(col)
             for col, val in set_values.items()]
    new_df = df.with_columns(exprs)
    after = _schema_map(new_df)

    if after != before:
        changed = {c: (before[c], after[c]) for c in before if before[c] != after[c]}
        return {"status": "error", "written": False, "matched_rows": n_match,
                "diagnostics": ["edição mudaria o schema do Parquet — abortado",
                                f"dtypes alterados: {changed}"]}

    if dry_run:
        return {"status": "ok", "written": False, "dry_run": True,
                "matched_rows": n_match, "schema_preserved": True}

    Path(backup_path(path)).write_bytes(Path(path).read_bytes())
    tmp = f"{path}.tmp"
    new_df.write_parquet(tmp)
    os.replace(tmp, path)
    return {"status": "ok", "written": True, "matched_rows": n_match,
            "schema_preserved": True, "artifacts": {"backup": backup_path(path)}}


# ── Localizar a raiz do caso (para revalidar com `novomodelo validate`) ─────────────

def find_case_dir(path: str, stop_at: list[Path] | None = None) -> str | None:
    """Pasta com `config.json` mais próxima acima de `path`.

    Com `stop_at` (as raízes do workspace), não sobe além da raiz que contém
    `path`: sem o limite, um `config.json` acima do workspace seria o caso.
    """
    p = Path(path).resolve()
    limit = next((r for r in stop_at or [] if p.is_relative_to(r)), None)
    for anc in [p if p.is_dir() else p.parent, *p.parents]:
        if limit is not None and not anc.is_relative_to(limit):
            return None
        if (anc / "config.json").exists():
            return str(anc)
    return None


# ── Mapa do caso: entradas listadas, rodadas resumidas (deck_list) ─────────────

#: Arquivos que contam como entrada do caso.
_INPUT_SUFFIXES = (".json", ".parquet")


def is_run_output(d: Path) -> bool:
    """Uma pasta é saída de rodada quando tem `training/metadata.json`.

    É o contrato de saída documentado do novomodelo (o mesmo que as tools
    `results_*` usam), não um palpite pelo nome da pasta (`output/`, `output_2/`…).
    """
    return (d / "training" / "metadata.json").is_file()


def _summarize_run(root: Path, d: Path) -> dict[str, Any]:
    n_files = n_bytes = 0
    for dirpath, _dirs, files in os.walk(d):
        for f in files:
            n_files += 1
            try:
                n_bytes += (Path(dirpath) / f).stat().st_size
            except OSError:
                pass
    sim = d / "simulation"
    entities = sorted(p.name for p in sim.iterdir() if p.is_dir()) if sim.is_dir() else []
    rel = d.relative_to(root).as_posix() if d != root else "."
    return {"path": str(d), "rel": rel, "files": n_files, "bytes": n_bytes,
            "milestones": {"training": (d / "training" / "_SUCCESS").exists(),
                           "simulation": (sim / "_SUCCESS").exists()},
            "simulation_entities": entities,
            "next": f"results_status(output_dir='{d}') para status; results_query para dados"}


def case_map(case_dir: str, schema_types: set[str], max_files: int,
             max_other: int = 50) -> dict[str, Any]:
    """Mapa de um caso: o que é entrada, o que é rodada e o que é outra coisa.

    - entradas: `.json`/`.parquet` fora das rodadas, um a um (caminho, tamanho e o
      tipo de schema quando o nome do arquivo corresponde a um; ex. hydros.json →
      `hydros`), com teto `max_files`;
    - rodadas: cada pasta de saída numa linha (nº de arquivos, bytes, marcos);
      o conteúdo NÃO é listado, porque as `results_*` já conhecem o formato;
    - outros: demais arquivos (backups, dashboard…), só o nome, com teto.
    """
    root = Path(case_dir)
    inputs: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    others: list[str] = []
    n_inputs = n_others = 0
    for dirpath, dirs, files in os.walk(root):
        here = Path(dirpath)
        if is_run_output(here):
            runs.append(_summarize_run(root, here))
            dirs[:] = []          # não desce na rodada
            continue
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for f in sorted(files):
            if f.startswith("."):
                continue
            p = here / f
            rel = p.relative_to(root).as_posix()
            if p.suffix in _INPUT_SUFFIXES:
                n_inputs += 1
                if len(inputs) < max_files:
                    item = {"path": str(p), "rel": rel, "kind": p.suffix.lstrip("."),
                            "bytes": p.stat().st_size}
                    if p.stem in schema_types:
                        item["schema"] = p.stem
                    inputs.append(item)
            else:
                n_others += 1
                if len(others) < max_other:
                    others.append(rel)
    out: dict[str, Any] = {"status": "ok", "case_dir": str(root),
                           "count": n_inputs, "files": inputs,
                           "runs": runs, "others": others}
    if n_inputs > len(inputs):
        out["files_truncated"] = True
    if n_others > len(others):
        out["others_total"] = n_others
    return out
