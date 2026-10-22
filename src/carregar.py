"""Leitura da tabela de vendas e validação do schema.

Escolha da fonte: se dados/bruto/ tiver arquivos, usa a fonte real (config.FONTE_REAL);
se estiver vazia, usa a amostra sintética de dados/amostra/. Mensagens de erro nunca
mostram valores das células, só nomes de colunas e contagens.
"""
import pandas as pd

from src import config as C


class ErroSchema(Exception):
    pass


def tem_dados_reais():
    return C.DIR_BRUTO.exists() and any(
        p.is_file() and p.name not in C.ARQUIVOS_IGNORADOS for p in C.DIR_BRUTO.rglob("*"))


def escolher_fonte(fonte="auto"):
    if fonte == "auto":
        fonte = "real" if tem_dados_reais() else "amostra"
    if fonte == "real":
        return "real", C.FONTE_REAL, C.DIR_BRUTO
    return "amostra", C.FONTE_AMOSTRA, C.DIR_AMOSTRA


def _validar_config(fonte, cfg):
    faltando = [k for k in ("arquivo",) if not cfg.get(k)]
    faltando += [f"colunas.{k}" for k, v in cfg["colunas"].items() if not v]
    if faltando:
        raise ErroSchema(
            f"Fonte '{fonte}' sem schema configurado ({', '.join(faltando)}). "
            "Preencha src/config.py a partir de relatorios/perfil_dados.md.")


def _ler(caminho, cfg):
    ext = caminho.suffix.lower()
    if ext in {".csv", ".txt", ".tsv"}:
        return pd.read_csv(caminho, sep=cfg["sep"], encoding=cfg["encoding"], dtype=str,
                           skiprows=cfg["linhas_titulo"])
    return pd.read_excel(caminho, sheet_name=cfg["aba"] or 0, dtype=object,
                         skiprows=cfg["linhas_titulo"])


VERDADEIROS = {"true", "1", "1.0", "sim", "s", "verdadeiro", "x"}


def _booleano(s):
    return s.astype("string").str.strip().str.lower().isin(VERDADEIROS)


def _numero(s, decimal):
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float)
    t = s.astype("string").str.strip().str.replace(r"\s", "", regex=True)
    if decimal == ",":
        t = t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(t, errors="coerce")


def carregar_vendas(fonte="auto"):
    """Retorna (df, info). df tem as colunas internas data/sku/m2 + as originais restantes."""
    fonte, cfg, pasta = escolher_fonte(fonte)
    _validar_config(fonte, cfg)
    caminho = pasta / cfg["arquivo"]
    if not caminho.exists():
        raise ErroSchema(f"Arquivo configurado não encontrado: {caminho.name} em {pasta.name}/")

    bruto = _ler(caminho, cfg)
    bruto.columns = [str(c).strip() for c in bruto.columns]
    opcionais = list(cfg.get("filtro_verdadeiro") or []) + [
        c for c in (cfg.get("col_mes_parcial"), cfg.get("col_ruptura")) if c]
    ausentes = [orig for orig in list(cfg["colunas"].values()) + opcionais if orig not in bruto.columns]
    if ausentes:
        raise ErroSchema(f"Colunas ausentes em {caminho.name}: {ausentes}. "
                         f"O arquivo tem {bruto.shape[1]} colunas; confira o perfil.")

    info_filtro = {}
    for col in cfg.get("filtro_verdadeiro") or []:
        manter = _booleano(bruto[col])
        info_filtro[f"linhas_fora_por_{col}"] = int((~manter).sum())
        bruto = bruto[manter]
    df = bruto.rename(columns={v: k for k, v in cfg["colunas"].items()})
    df["mes_parcial"] = _booleano(df[cfg["col_mes_parcial"]]) if cfg.get("col_mes_parcial") else False
    df["ruptura"] = _booleano(df[cfg["col_ruptura"]]) if cfg.get("col_ruptura") else False
    n_nao_nulos = {c: int(df[c].notna().sum()) for c in (C.COL_DATA, C.COL_QTD)}
    if pd.api.types.is_datetime64_any_dtype(df[C.COL_DATA]):
        df[C.COL_DATA] = pd.to_datetime(df[C.COL_DATA])
    else:
        df[C.COL_DATA] = pd.to_datetime(df[C.COL_DATA], errors="coerce",
                                        dayfirst=cfg["dayfirst"], format="mixed")
    df[C.COL_QTD] = _numero(df[C.COL_QTD], cfg["decimal"])
    df[C.COL_SKU] = df[C.COL_SKU].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)

    info = {"fonte": fonte, "arquivo": caminho.name, "linhas_lidas": len(df), **info_filtro}
    for c, n in n_nao_nulos.items():
        info[f"{c}_nao_convertidos"] = n - int(df[c].notna().sum())
    # Tolerância: linhas de total/rodapé costumam falhar na conversão; preparar.py as remove.
    for c in (C.COL_DATA, C.COL_QTD):
        if n_nao_nulos[c] and info[f"{c}_nao_convertidos"] / n_nao_nulos[c] > 0.05:
            raise ErroSchema(f"Mais de 5% de '{c}' não converteu ({info[f'{c}_nao_convertidos']} "
                             f"de {n_nao_nulos[c]}). Revise formato/decimal no config.")
    return df, info
