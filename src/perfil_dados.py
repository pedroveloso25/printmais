"""Perfil dos dados brutos da Print Mais — SÓ METADADOS AGREGADOS.

Uso:  python -m src.perfil_dados [pasta_entrada] [arquivo_saida]
      (padrão: dados/bruto  ->  relatorios/perfil_dados.md)

Os dados são sigilosos. Este script NUNCA escreve valores individuais de texto
(nomes de produtos, clientes, fornecedores, códigos). Para cada arquivo/aba ele
gera apenas: dimensões, tipos, % de nulos, cardinalidade, estatísticas de
colunas numéricas e de datas, comprimento médio de textos, duplicatas exatas e
taxas de casamento entre possíveis chaves de junção.

Mensagens de erro passam por `_sanitizar` (remove trechos entre aspas, que é
onde o pandas costuma ecoar valores das células).
"""
import csv
import io
import re
import sys
import traceback
import unicodedata
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ENTRADA = Path(sys.argv[1] if len(sys.argv) > 1 else "dados/bruto")
SAIDA = Path(sys.argv[2] if len(sys.argv) > 2 else "relatorios/perfil_dados.md")

IGNORAR = {".gitkeep", "COMO_OBTER.md"}
EXT_PLANILHA = {".xlsx", ".xlsm", ".xls", ".ods", ".xlsb"}
EXT_TEXTO = {".csv", ".txt", ".tsv"}
ENCODINGS = ["utf-8-sig", "cp1252", "latin-1"]
SEPARADORES = [";", ",", "\t", "|"]

LIMIAR_NUM = 0.95     # fração dos não-nulos que precisa virar número
LIMIAR_DATA = 0.90    # fração dos não-nulos que precisa virar data
JANELA_CAB = 30       # linhas iniciais examinadas para achar o cabeçalho
MAX_NOME_COL = 60

# tokens de nome de coluna que sugerem chave de produto
TOKENS_CHAVE = {"cod", "codigo", "codprod", "cdprod", "sku", "item", "produto", "prod",
                "ref", "referencia", "ean", "gtin", "id", "idprod", "material"}
TOKENS_NAO_CHAVE = {"descricao", "desc", "nome", "obs", "observacao", "complemento"}
TOKENS_DATA = {"data", "dt", "dia", "emissao", "venc", "vencimento", "previsao", "chegada",
               "entrada", "saida", "faturamento", "mes", "periodo", "competencia"}


# ---------------------------------------------------------------- utilidades
def _sanitizar(msg):
    msg = re.sub(r"'[^']*'", "'…'", str(msg))
    msg = re.sub(r'"[^"]*"', '"…"', msg)
    return msg[:300]


def _norm_nome(nome):
    s = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _tokens(nome):
    return set(t for t in _norm_nome(nome).split("_") if t)


def _md(x):
    return str(x).replace("|", "\\|").replace("\n", " ")


def _fmt(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, (pd.Timestamp,)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}".replace(",", ".")
    if isinstance(v, (float, np.floating)):
        if float(v).is_integer() and abs(v) < 1e15:
            return f"{int(v):,}".replace(",", ".")
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return _md(v)


# ---------------------------------------------------------------- leitura
def _detectar_encoding(caminho):
    bruto = caminho.read_bytes()
    for enc in ENCODINGS:
        try:
            return bruto.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1", errors="replace"), "latin-1 (com substituição)"


def _detectar_sep(texto):
    amostra = "\n".join(texto.splitlines()[:200])
    try:
        return csv.Sniffer().sniff(amostra, delimiters="".join(SEPARADORES)).delimiter
    except csv.Error:
        contagem = {s: amostra.count(s) for s in SEPARADORES}
        return max(contagem, key=contagem.get)


def _ler_texto(caminho):
    texto, enc = _detectar_encoding(caminho)
    sep = _detectar_sep(texto)
    df = pd.read_csv(io.StringIO(texto), sep=sep, header=None, dtype=str,
                     keep_default_na=True, skip_blank_lines=False,
                     engine="python", on_bad_lines="warn")
    nome_sep = {";": "ponto e vírgula", ",": "vírgula", "\t": "tab", "|": "pipe"}[sep]
    return {"(arquivo)": df}, f"encoding={enc}; separador={nome_sep}"


def _parece_html(caminho):
    inicio = caminho.read_bytes()[:2048].lower()
    return b"<html" in inicio or b"<table" in inicio or b"<!doctype" in inicio


def _ler_planilha(caminho):
    ext = caminho.suffix.lower()
    if ext == ".xls" and _parece_html(caminho):
        tabelas = pd.read_html(caminho, header=None)
        return ({f"tabela_{i + 1}": t for i, t in enumerate(tabelas)},
                "formato=HTML disfarçado de .xls")
    motor = {".xls": "xlrd", ".ods": "odf", ".xlsb": "pyxlsb"}.get(ext, "openpyxl")
    try:
        abas = pd.read_excel(caminho, sheet_name=None, header=None, engine=motor)
    except ImportError as e:
        raise RuntimeError(f"falta a biblioteca do motor '{motor}' (pip install {motor})") from e
    return abas, f"motor={motor}"


# ---------------------------------------------------------------- cabeçalho
def _e_texto_rotulo(v):
    if pd.isna(v):
        return False
    if isinstance(v, str):
        s = v.strip()
        return bool(s) and not re.fullmatch(r"[-+]?[\d.,/:\s]+", s)
    return False


def _detectar_cabecalho(bruto):
    """Primeira linha (nas JANELA_CAB iniciais) quase cheia e composta de rótulos de texto."""
    janela = bruto.head(JANELA_CAB)
    preench = janela.notna().sum(axis=1)
    if preench.max() == 0:
        return None
    alvo = 0.6 * preench.max()
    for i in janela.index:
        linha = janela.loc[i]
        n = linha.notna().sum()
        if n < max(alvo, 1):
            continue
        rotulos = sum(_e_texto_rotulo(v) for v in linha)
        if rotulos / n >= 0.8:
            return i
    return None


def _montar_tabela(bruto):
    bruto = bruto.dropna(how="all").dropna(axis=1, how="all")
    info = {}
    i_cab = _detectar_cabecalho(bruto)
    if i_cab is None:
        info["cabecalho"] = "não detectado (colunas nomeadas col_1, col_2…)"
        df = bruto.copy()
        df.columns = [f"col_{k + 1}" for k in range(df.shape[1])]
    else:
        pos = bruto.index.get_loc(i_cab)
        info["cabecalho"] = f"linha {pos + 1} das não vazias" + (
            f" ({pos} linha(s) de título descartada(s))" if pos else "")
        nomes, vistos = [], {}
        for k, v in enumerate(bruto.loc[i_cab]):
            n = str(v).strip()[:MAX_NOME_COL] if _e_texto_rotulo(v) else f"col_{k + 1}"
            vistos[n] = vistos.get(n, 0) + 1
            nomes.append(n if vistos[n] == 1 else f"{n}__{vistos[n]}")
        df = bruto.iloc[pos + 1:].copy()
        df.columns = nomes
    df = df.dropna(how="all").reset_index(drop=True).infer_objects()
    # repetições do cabeçalho no meio do arquivo (relatórios paginados)
    if i_cab is not None:
        cab = [str(c) for c in df.columns]
        rep = df.astype(str).apply(lambda r: sum(a == b for a, b in zip(r, cab)) >= 0.8 * len(cab), axis=1)
        info["cabecalhos_repetidos_removidos"] = int(rep.sum())
        df = df[~rep].reset_index(drop=True)
    return df, info


# ---------------------------------------------------------------- inferência
def _para_numero(s):
    """Converte série de texto para número aceitando 1.234,56 (pt-BR) e 1,234.56 / 1234.56."""
    t = s.astype(str).str.strip().str.replace(r"^R\$\s*", "", regex=True).str.replace("%", "", regex=False)
    t = t.str.replace(r"\s", "", regex=True)
    br = t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    en = t.str.replace(",", "", regex=False)
    n_br = pd.to_numeric(br, errors="coerce")
    n_en = pd.to_numeric(en, errors="coerce")
    tem_virgula = t.str.contains(",", regex=False).mean() > 0
    return (n_br if tem_virgula and n_br.notna().sum() >= n_en.notna().sum() else n_en), \
        ("pt-BR" if tem_virgula and n_br.notna().sum() >= n_en.notna().sum() else "padrão")


def _para_data(s):
    t = s.astype(str).str.strip()
    # exige algo com cara de data, para não transformar códigos em datas
    cara = t.str.contains(r"\d{1,4}[/\-.]\d{1,2}(?:[/\-.]\d{1,4})?", regex=True)
    if cara.mean() < LIMIAR_DATA:
        return None
    return pd.to_datetime(t.where(cara), errors="coerce", dayfirst=True, format="mixed")


def _inferir(col, nome):
    """Retorna (série convertida, tipo, observação)."""
    nn = col.dropna()
    if nn.empty:
        return col, "vazia", ""
    if pd.api.types.is_datetime64_any_dtype(col):
        return col, "data", ""
    convertida = pd.to_datetime(nn, errors="coerce") if nn.map(
        lambda v: isinstance(v, (pd.Timestamp, np.datetime64)) or hasattr(v, "year")).mean() >= LIMIAR_DATA else None
    if convertida is not None and convertida.notna().mean() >= LIMIAR_DATA:
        return pd.to_datetime(col, errors="coerce"), "data", "nativa da planilha"

    if pd.api.types.is_numeric_dtype(col):
        num, obs = col.astype(float), ""
    else:
        num, fmt = _para_numero(nn)
        if num.notna().mean() >= LIMIAR_NUM:
            num = num.reindex(col.index)
            obs = f"número em texto ({fmt}); {nn.size - num.notna().sum()} não convertido(s)"
        else:
            num = None
    if num is not None:
        nome_data = bool(_tokens(nome) & TOKENS_DATA)
        v = num.dropna()
        if nome_data and len(v) and v.between(20000, 60000).mean() >= LIMIAR_DATA:
            d = pd.to_datetime(num, unit="D", origin="1899-12-30", errors="coerce")
            return d, "data", "serial do Excel"
        if nome_data and len(v) and v.between(19000101, 21001231).mean() >= LIMIAR_DATA:
            d = pd.to_datetime(num.astype("Int64").astype(str), format="%Y%m%d", errors="coerce")
            if d.notna().sum() >= LIMIAR_DATA * len(v):
                return d, "data", "número AAAAMMDD"
        return num, "numérica", obs

    d = _para_data(nn)
    if d is not None and d.notna().mean() >= LIMIAR_DATA:
        return pd.to_datetime(d.reindex(col.index)), "data", "texto convertido"
    return col.astype("string"), "texto", ""


# ---------------------------------------------------------------- perfis
def _perfil_data(d):
    d = d.dropna()
    if d.empty:
        return {}
    meses = d.dt.to_period("M")
    todos = pd.period_range(meses.min(), meses.max(), freq="M")
    presentes = set(meses.unique())
    faltando = [str(m) for m in todos if m not in presentes]
    ini, fim = d.min(), d.max()
    return {
        "min": ini, "max": fim,
        "meses_no_intervalo": len(todos),
        "meses_com_registro": len(presentes),
        "meses_sem_registro": faltando,
        "1o_mes_parcial": ini.day > 1,
        "ultimo_mes_parcial": fim.day < fim.days_in_month,
        "fora_de_faixa": int(((d < "2000-01-01") | (d > "2030-12-31")).sum()),
    }


def _perfil_num(x):
    x = x.dropna()
    if x.empty:
        return {}
    q = x.quantile([0, .25, .5, .75, 1])
    return {"min": q[0], "p25": q[.25], "mediana": q[.5], "p75": q[.75], "max": q[1],
            "zeros": int((x == 0).sum()), "negativos": int((x < 0).sum()),
            "inteiros": bool((x % 1 == 0).all())}


def _chave_normalizada(s):
    t = s.dropna().astype(str).str.strip().str.upper()
    t = t.str.replace(r"\.0+$", "", regex=True).str.lstrip("0")
    return set(t[t != ""])


def perfil_tabela(df):
    colunas, convertidas = [], {}
    for nome in df.columns:
        serie, tipo, obs = _inferir(df[nome], nome)
        convertidas[nome] = serie
        c = {"nome": nome, "tipo": tipo, "obs": obs,
             "nulos_pct": 100 * df[nome].isna().mean(),
             "distintos": int(serie.nunique(dropna=True))}
        if tipo == "data":
            c["data"] = _perfil_data(serie)
        elif tipo == "numérica":
            c["num"] = _perfil_num(serie)
        elif tipo == "texto":
            nn = serie.dropna()
            c["compr_medio"] = float(nn.str.len().mean()) if len(nn) else np.nan
        colunas.append(c)
    total = df.astype(str).apply(lambda r: r.str.contains(r"\b(?:sub)?total\b", case=False, regex=True).any(), axis=1)
    return {
        "linhas": len(df), "colunas": df.shape[1],
        "duplicadas": int(df.duplicated().sum()),
        "linhas_total": int(total.sum()),
        "cols": colunas,
    }, convertidas


def _candidata_chave(c):
    tk = _tokens(c["nome"])
    if not (tk & TOKENS_CHAVE) or (tk & TOKENS_NAO_CHAVE):
        return False
    if c["tipo"] == "numérica":
        return c.get("num", {}).get("inteiros", False) and c["distintos"] > 1
    if c["tipo"] == "texto":
        return c["distintos"] > 1 and (c.get("compr_medio") or 99) <= 30
    return False


def casamentos(tabelas):
    """tabelas: {rotulo: (perfil, convertidas)} -> lista de pares de chaves e taxas."""
    cand = []
    for rot, (perf, conv) in tabelas.items():
        for c in perf["cols"]:
            if _candidata_chave(c):
                cand.append((rot, c["nome"], _chave_normalizada(conv[c["nome"]])))
    pares = []
    for (ra, ca, va), (rb, cb, vb) in combinations(cand, 2):
        if ra == rb or not va or not vb:
            continue
        inter = len(va & vb)
        pares.append({"a": f"{ra} → {ca}", "b": f"{rb} → {cb}",
                      "dist_a": len(va), "dist_b": len(vb),
                      "a_em_b": 100 * inter / len(va), "b_em_a": 100 * inter / len(vb),
                      "mesmo_nome": _norm_nome(ca) == _norm_nome(cb)})
    pares.sort(key=lambda p: -max(p["a_em_b"], p["b_em_a"]))
    return pares


# ---------------------------------------------------------------- relatório
def _secao_tabela(rot, meta, perf):
    L = [f"### {_md(rot)}", ""]
    for k, v in meta.items():
        L.append(f"- {k}: {_md(v)}")
    L += [f"- linhas: {_fmt(perf['linhas'])} | colunas: {perf['colunas']}",
          f"- linhas duplicadas exatas: {_fmt(perf['duplicadas'])}",
          f"- linhas com a palavra 'total'/'subtotal' em alguma célula: {_fmt(perf['linhas_total'])}", "",
          "| coluna | tipo | % nulos | distintos | obs |", "|---|---|---:|---:|---|"]
    for c in perf["cols"]:
        L.append(f"| {_md(c['nome'])} | {c['tipo']} | {c['nulos_pct']:.1f} | {_fmt(c['distintos'])} | {_md(c['obs'])} |")

    datas = [c for c in perf["cols"] if c["tipo"] == "data" and c.get("data")]
    if datas:
        L += ["", "**Datas**", "",
              "| coluna | mín | máx | meses no intervalo | meses com registro | 1º mês parcial | último mês parcial | fora de 2000–2030 | meses sem registro |",
              "|---|---|---|---:|---:|---|---|---:|---|"]
        for c in datas:
            d = c["data"]
            falt = ", ".join(d["meses_sem_registro"]) if d["meses_sem_registro"] else "nenhum"
            L.append(f"| {_md(c['nome'])} | {_fmt(d['min'])} | {_fmt(d['max'])} | {d['meses_no_intervalo']} | "
                     f"{d['meses_com_registro']} | {'sim' if d['1o_mes_parcial'] else 'não'} | "
                     f"{'sim' if d['ultimo_mes_parcial'] else 'não'} | {d['fora_de_faixa']} | {falt} |")

    nums = [c for c in perf["cols"] if c["tipo"] == "numérica" and c.get("num")]
    if nums:
        L += ["", "**Numéricas**", "",
              "| coluna | mín | p25 | mediana | p75 | máx | zeros | negativos | só inteiros |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
        for c in nums:
            n = c["num"]
            L.append(f"| {_md(c['nome'])} | {_fmt(n['min'])} | {_fmt(n['p25'])} | {_fmt(n['mediana'])} | "
                     f"{_fmt(n['p75'])} | {_fmt(n['max'])} | {_fmt(n['zeros'])} | {_fmt(n['negativos'])} | "
                     f"{'sim' if n['inteiros'] else 'não'} |")

    txts = [c for c in perf["cols"] if c["tipo"] == "texto"]
    if txts:
        L += ["", "**Texto** (só comprimento médio e cardinalidade)", "",
              "| coluna | compr. médio | distintos |", "|---|---:|---:|"]
        for c in txts:
            L.append(f"| {_md(c['nome'])} | {_fmt(c['compr_medio'])} | {_fmt(c['distintos'])} |")
    return L + [""]


def main():
    arquivos = sorted(p for p in ENTRADA.rglob("*") if p.is_file() and p.name not in IGNORAR)
    tabelas, secoes, erros = {}, [], []
    resumo = ["| arquivo / aba | MB | linhas | colunas | duplicadas | status |", "|---|---:|---:|---:|---:|---|"]

    for arq in arquivos:
        rel = arq.relative_to(ENTRADA).as_posix()
        mb = arq.stat().st_size / 1_048_576
        ext = arq.suffix.lower()
        try:
            if ext in EXT_PLANILHA:
                abas, meta_arq = _ler_planilha(arq)
            elif ext in EXT_TEXTO:
                abas, meta_arq = _ler_texto(arq)
            else:
                resumo.append(f"| {_md(rel)} | {mb:.2f} | — | — | — | ignorado (extensão {ext or 'nenhuma'}) |")
                continue
        except Exception as e:
            erros.append(f"- **{_md(rel)}**: {type(e).__name__}: {_sanitizar(e)}")
            resumo.append(f"| {_md(rel)} | {mb:.2f} | — | — | — | ERRO na leitura |")
            continue

        for aba, bruto in abas.items():
            rot = rel if aba == "(arquivo)" else f"{rel} [{aba}]"
            try:
                df, meta = _montar_tabela(bruto)
                perf, conv = perfil_tabela(df)
                tabelas[rot] = (perf, conv)
                meta = {"leitura": meta_arq, "tamanho do arquivo (MB)": f"{mb:.2f}", **meta}
                secoes += _secao_tabela(rot, meta, perf)
                resumo.append(f"| {_md(rot)} | {mb:.2f} | {_fmt(perf['linhas'])} | {perf['colunas']} | "
                              f"{_fmt(perf['duplicadas'])} | ok |")
            except Exception as e:
                quadro = traceback.extract_tb(e.__traceback__)[-1]
                erros.append(f"- **{_md(rot)}**: {type(e).__name__} (linha {quadro.lineno} do script): {_sanitizar(e)}")
                resumo.append(f"| {_md(rot)} | {mb:.2f} | — | — | — | ERRO no perfil |")

    pares = casamentos(tabelas)

    L = ["# Perfil dos dados brutos (somente metadados agregados)", "",
         f"Pasta: `{ENTRADA.as_posix()}` — {len(arquivos)} arquivo(s), {len(tabelas)} tabela(s) perfiladas.",
         "Nenhum valor individual de texto é exibido. Datas e numéricas mostram só resumos.", "",
         "## Resumo", ""] + resumo + [""]
    if erros:
        L += ["## Erros", ""] + erros + [""]
    L += ["## Possíveis chaves de junção", "",
          "Colunas cujo nome sugere código de produto/item (inteiras ou texto curto). "
          "Valores normalizados (maiúsculas, sem espaços, sem '.0' e zeros à esquerda). "
          "Taxa = % dos valores distintos de um lado presentes no outro.", ""]
    if pares:
        L += ["| coluna A | coluna B | distintos A | distintos B | % A em B | % B em A | mesmo nome |",
              "|---|---|---:|---:|---:|---:|---|"]
        for p in pares:
            L.append(f"| {_md(p['a'])} | {_md(p['b'])} | {_fmt(p['dist_a'])} | {_fmt(p['dist_b'])} | "
                     f"{p['a_em_b']:.1f} | {p['b_em_a']:.1f} | {'sim' if p['mesmo_nome'] else 'não'} |")
    else:
        L.append("Nenhum par de colunas candidatas entre tabelas diferentes.")
    L += ["", "## Detalhe por tabela", ""] + secoes

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text("\n".join(L), encoding="utf-8")
    print(f"{len(tabelas)} tabela(s) perfiladas, {len(erros)} erro(s). Relatório: {SAIDA}")


if __name__ == "__main__":
    main()
