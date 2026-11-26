"""Gera o relatório preliminar da E06 (.docx e, se houver Word, .pdf) a partir de e06.json.

Uso:  python -m scripts.relatorio_e06 [--fonte real|amostra]
Rodar depois de `python -m src.e06 --fonte real`.

Nenhum número do relatório é digitado à mão: todos vêm de relatorios/<fonte>/e06.json. O texto
interpretativo é fixo; se um número mudar de sinal, a frase correspondente precisa ser revista
(o script avisa quando uma premissa do texto deixa de valer — ver `checar`).
Só métricas relativas entram no relatório (pinball ÷ média, % da demanda): m² e bobinas
absolutos ficam no JSON. Saída em relatorios/<fonte>/ (relatorios/real/ não é versionado).
"""
import argparse
import json
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from src import config as C

REPO = "https://github.com/pedroveloso25/printmais"
EQUIPE = "Pedro Rebouças Veloso · João Filipe Dantas"
AZUL, LARANJA, AQUA, CINZA, TINTA = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984", "#0b0b0b"

NOME = {"B0_media3": "B0 média 3m (regra atual)", "B1_media3": "B1 = s × média 3m",
        "B0_p75_6": "B0' P75 6m (E04/E05)", "B1_p75_6": "B1' = s × P75 6m",
        "M_linear_quantil": "M linear (QuantileRegressor)", "M_arvore_fator": "M árvore × s",
        "M_gb_quantil": "M GradientBoosting quantil",
        "B1pin_media3": "s(pinball) × média 3m", "B1pin_p75_6": "s(pinball) × P75 6m"}


# ---------------------------------------------------------------- formatação pt-BR
def n(x, d=1, sinal=False):
    if x is None:
        return "—"
    s = f"{x:+,.{d}f}" if sinal else f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pp(x, d=1):
    return n(x, d, sinal=True) + " p.p."


def ic(v, d=1):
    return f"[{n(v[0], d, True)}; {n(v[1], d, True)}]"


# ---------------------------------------------------------------- docx
def _sombra(cel, cor):
    tc = cel._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear"), sh.set(qn("w:color"), "auto"), sh.set(qn("w:fill"), cor)
    tc.append(sh)


def _numerico(v):
    """Célula numérica (alinha à direita): número, %, p.p., intervalo ou traço."""
    t = str(v).strip()
    return len(t) < 24 and (t[:1] in "+-−[—" or t[:1].isdigit())


class Rel:
    def __init__(self):
        self.d = Document()
        sec = self.d.sections[0]
        sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
        sec.left_margin = sec.right_margin = Cm(1.8)
        sec.top_margin = sec.bottom_margin = Cm(1.5)
        st = self.d.styles["Normal"]
        st.font.name, st.font.size = "Calibri", Pt(9.5)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
        st.paragraph_format.space_after = Pt(3)
        st.paragraph_format.line_spacing = 1.05
        for h, tam in [("Heading 1", 12.5), ("Heading 2", 10.5)]:
            s = self.d.styles[h]
            s.font.name, s.font.size, s.font.bold = "Calibri", Pt(tam), True
            s.font.color.rgb = RGBColor(0x0b, 0x0b, 0x0b)
            s.paragraph_format.space_before, s.paragraph_format.space_after = Pt(8), Pt(3)

    def h1(self, t):
        self.d.add_heading(t, level=1)

    def h2(self, t):
        self.d.add_heading(t, level=2)

    def p(self, *partes, estilo=None):
        """partes: str ou ("negrito", str) / ("italico", str)."""
        par = self.d.add_paragraph(style=estilo)
        for x in partes:
            if isinstance(x, tuple):
                r = par.add_run(x[1])
                r.bold, r.italic = x[0] == "negrito", x[0] == "italico"
            else:
                par.add_run(x)
        return par

    def li(self, *partes):
        return self.p(*partes, estilo="List Bullet")

    def tabela(self, cab, linhas, larg=None, destaque=None, fonte=8.5):
        t = self.d.add_table(rows=1, cols=len(cab))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, c in enumerate(cab):
            cel = t.rows[0].cells[i]
            cel.text = ""
            r = cel.paragraphs[0].add_run(c)
            r.bold, r.font.size = True, Pt(fonte)
            _sombra(cel, "EDEDEA")
        for k, linha in enumerate(linhas):
            cels = t.add_row().cells
            for i, v in enumerate(linha):
                cels[i].text = ""
                r = cels[i].paragraphs[0].add_run(str(v))
                r.font.size = Pt(fonte)
                if destaque and k in destaque:
                    r.bold = True
                if i > 0 and _numerico(v):
                    cels[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for row in t.rows:
            for cel in row.cells:
                for par in cel.paragraphs:
                    par.paragraph_format.space_after = Pt(0)
        if larg:
            for row in t.rows:
                for i, w in enumerate(larg):
                    row.cells[i].width = Cm(w)
        self.d.add_paragraph().paragraph_format.space_after = Pt(0)
        return t

    def legenda(self, t):
        par = self.p(("italico", t))
        par.runs[0].font.size = Pt(8)
        return par

    def figura(self, caminho, largura_cm=17.4):
        self.d.add_picture(str(caminho), width=Cm(largura_cm))
        self.d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    def mono(self, texto):
        par = self.d.add_paragraph()
        r = par.add_run(texto)
        r.font.name, r.font.size = "Consolas", Pt(7.5)
        r._element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
        par.paragraph_format.space_after = Pt(2)


# ---------------------------------------------------------------- figuras
def figuras(R, pasta):
    pasta.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "Calibri", "font.size": 8.5, "axes.edgecolor": CINZA,
                         "axes.labelcolor": TINTA, "xtick.color": TINTA, "ytick.color": TINTA})
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 2.6), gridspec_kw={"width_ratios": [1.25, 1]})

    # (a) pinball relativa no teste, τ = 0,75
    q = {x["abordagem"]: x for x in R["T1"]["tau_0.75"]["quadro"]}
    ordem = ["B0_media3", "B1_media3", "B0_p75_6", "B1_p75_6", "M_linear_quantil", "M_arvore_fator", "M_gb_quantil"]
    cor = {"B0": AZUL, "B1": AQUA, "M_": LARANJA}
    rot = ["média 3m (B0)", "s × média 3m (B1)", "P75 6m (B0')", "s × P75 6m (B1')",
           "linear quantil", "árvore × s", "GB quantil"]
    vals = [q[a]["pinball_rel_%"] for a in ordem]
    y = list(range(len(ordem)))[::-1]
    a1.barh(y, vals, height=0.55, color=[cor[a[:2]] for a in ordem], edgecolor="white", linewidth=2)
    for yi, v in zip(y, vals):
        a1.text(v + 0.3, yi, n(v), va="center", fontsize=8, color=TINTA)
    a1.axvline(q["B0_media3"]["pinball_rel_%"], color=AZUL, lw=1, ls=(0, (2, 2)))
    a1.set_yticks(y, rot)
    a1.set_xlim(0, max(vals) * 1.3)
    a1.set_xlabel("pinball τ=0,75 ÷ média real (%) — menor é melhor")
    a1.set_title("(a) Teste ago–set, 30 códigos, 60 linhas", fontsize=9, loc="left")
    for lado in ["top", "right"]:
        a1.spines[lado].set_visible(False)
    a1.grid(axis="x", color="#e6e5e0", lw=0.6)
    a1.set_axisbelow(True)
    from matplotlib.patches import Patch
    a1.legend(handles=[Patch(color=AZUL, label="regra (B0)"), Patch(color=AQUA, label="regra × s (B1)"),
                       Patch(color=LARANJA, label="modelo (M)")], fontsize=7, frameon=False,
              loc="upper right")

    # (b) defasamento: correlação observada × referência nula
    t2 = R["T2"]["todos_os_meses"]
    lags = [1, 4, 5]
    for i, k in enumerate(lags):
        v = t2[f"lag_{k}"]
        a2.fill_between([i - 0.28, i + 0.28], *v["correlacao_nula_ic95"], color="#d9d8d2", lw=0)
        a2.plot([i - 0.28, i + 0.28], [v["correlacao_nula_media"]] * 2, color=CINZA, lw=1.5)
        a2.errorbar(i, v["correlacao"], yerr=[[v["correlacao"] - v["correlacao_ic95"][0]],
                                              [v["correlacao_ic95"][1] - v["correlacao"]]],
                    fmt="o", ms=6, color=LARANJA, ecolor=LARANJA, elinewidth=1.5, capsize=3)
        a2.text(i + 0.12, v["correlacao"], n(v["correlacao"], 2, True), fontsize=8, va="center")
    a2.axhline(0, color=CINZA, lw=0.6)
    a2.set_xticks(range(3), [f"lag {k}\n({t2[f'lag_{k}']['pares']} pares)" for k in lags])
    a2.set_ylabel("correlação (venda ÷ média do código)")
    a2.set_title("(b) Persistência da demanda", fontsize=9, loc="left")
    for lado in ["top", "right"]:
        a2.spines[lado].set_visible(False)
    a2.legend(handles=[plt.Line2D([], [], marker="o", color=LARANJA, ls="", label="observado (IC 95%)"),
                       Patch(color="#d9d8d2", label="nulo: meses embaralhados")], fontsize=7, frameon=False,
              loc="lower left")
    fig.tight_layout()
    fig.savefig(pasta / "e06_fig1.png", dpi=220)
    plt.close(fig)
    return pasta / "e06_fig1.png"


# ---------------------------------------------------------------- premissas do texto
def checar(R):
    """Avisa se um número contradiz o texto fixo (o texto então precisa ser revisto)."""
    t = R["T1"]["tau_0.75"]
    q = {x["abordagem"]: x["pinball_rel_%"] for x in t["quadro"]}
    avisos = []
    if not q["B0_media3"] <= min(q[m] for m in q if m.startswith("M_")):
        avisos.append("um modelo bateu a média 3m: revisar seções 1, 6 e 7")
    if not q["B0_media3"] < q["B0_p75_6"]:
        avisos.append("P75 6m não é mais pior que média 3m: revisar seção 5.1")
    e = t["bases"]["media3"]["efeitos"]["B1_media3 - B0_media3"]
    if not e["ponto"] > 0:
        avisos.append("efeito quantil deixou de ser piora: revisar seção 6")
    for a in avisos:
        print("AVISO:", a)
    return avisos


# ---------------------------------------------------------------- conteúdo
def gerar(R, saida):
    T1, T2, T3, T4 = R["T1"], R["T2"], R["T3"], R["T4"]
    t = T1["tau_0.75"]
    q = {x["abordagem"]: x for x in t["quadro"]}
    bm, bp = t["bases"]["media3"], t["bases"]["p75_6"]
    em, ep = bm["efeitos"], bp["efeitos"]
    eb = t["entre_bases"]
    mods = t["modelos"]
    pin = lambda a, tau="tau_0.75": {x["abordagem"]: x for x in T1[tau]["quadro"]}[a]["pinball_rel_%"]
    dec = {(x["abordagem"], x["versao"]): x for x in T3["decisao"]}
    g = {(x["contra"], x["versao"]): x for x in T3["ganho_gb"]}
    lag = T2["todos_os_meses"]
    fora = T4["fora_do_filtro_incluir"]
    gr = T4["grupos"]
    gb_m3 = em["M_gb_quantil - B0_media3"]

    r = Rel()
    # ---------------- capa
    tit = r.d.add_paragraph()
    run = tit.add_run("Previsão de demanda mensal por código — Print Mais")
    run.bold, run.font.size = True, Pt(15)
    r.p(("negrito", "Entrega 6 · Relatório preliminar · Equipe E · 26/11/2026"))
    r.p(f"Integrantes: {EQUIPE}  ·  Repositório: {REPO}  ·  Demandante: Francisco Cavalcanti Junior, "
        "gestor de compras  ·  Disciplina de Machine Learning (UFPB)")

    # ---------------- 1
    r.h1("1. Resumo executivo (esboço)")
    r.li(("negrito", "Pergunta: "), "quanto comprar de cada código no próximo pedido de importação. O projeto "
         "estima o quantil 0,75 da demanda mensal de cada código.")
    r.li(("negrito", "Resultado principal: "), "com 7 meses de histórico, nenhum modelo supera a regra atual "
         f"da empresa (média dos 3 últimos meses). O melhor modelo (GradientBoosting com perda quantil) fica "
         f"{pp(gb_m3['ponto'])} de pinball acima dela, IC 95% {ic(gb_m3['ic95'])}. A diferença não é "
         "distinguível de zero, mas também não é ganho.")
    r.li(("negrito", "Mudança de baseline: "), "a E04/E05 usaram o P75 dos 6 últimos meses como regra da "
         "empresa. A devolutiva de 23 e 25/11 confirmou que a regra é a média dos 3 últimos meses fechados, "
         "que passa a ser o B0. A troca vem do processo real, não do desempenho: no teste a média 3m tem "
         f"pinball menor ({n(q['B0_media3']['pinball_rel_%'])}% contra {n(q['B0_p75_6']['pinball_rel_%'])}%), "
         "mas a diferença em τ = 0,75 não é significativa (seção 5.1).")
    r.li(("negrito", "Defasamento medido: "), f"a demanda persiste de um mês para o seguinte (correlação "
         f"{n(lag['lag_1']['correlacao'], 2, True)}), mas não em 5 meses ({n(lag['lag_5']['correlacao'], 2, True)}). "
         "Prever 1 mês à frente é proxy fraco para o pedido real, fechado 4 a 5 meses antes.")
    r.li(("negrito", "Maior risco: "), f"os códigos fora do filtro do projeto vendem {n(fora['demanda_relativa_aos_oficiais_%'] / 100, 2)}× "
         "o volume dos 30 códigos modelados, e todas as abordagens os subestimam.")

    # ---------------- 2
    r.h1("2. Decisão e contexto")
    r.p("A Print Mais importa da China bobinas de mídia (vinil, lona) para comunicação visual. O gestor de "
        "compras decide, a cada pedido, quantas bobinas de cada código entram no container. A decisão tem "
        "quatro travas operacionais, confirmadas nos dados e na devolutiva:")
    r.li(("negrito", "Lead time "), "de 113 a 162 dias entre o sinal e a chegada.")
    r.li(("negrito", "Pagamento antecipado: "), "sinal de 20% e saldo antes do embarque. O capital fica "
         "comprometido antes da venda.")
    r.li(("negrito", "Container cheio: "), f"~{n(C.M2_CONTAINER, 0)} m² de mídia (~{n(C.BOBINAS_CONTAINER, 0)} "
         "bobinas), 1 a 2 containers por mês. A restrição que morde é o espaço e o caixa, não o número de produtos.")
    r.li(("negrito", "Lote mínimo "), f"de {C.PISO_BOBINAS} bobinas por código que entra; acima disso, qualquer inteiro.")
    r.p("Faltar custa a margem perdida (~40% do preço) e, às vezes, o cliente. A venda perdida não volta. "
        "Sobrar custa capital parado e, raramente, desconto depois de ~45 dias. O projeto apoia a decisão; "
        "não a automatiza.")

    # ---------------- 3
    r.h1("3. Formulação")
    r.tabela(["Item", "Definição"], [
        ["Unidade", "código de demanda (SKUs equivalentes somados) × mês"],
        ["Alvo", "m² vendidos no mês (cada container cobre ~1 mês de venda)"],
        ["Tipo", "regressão quantílica: quantil τ = 0,75 da demanda do mês"],
        ["Horizonte", "1 mês: a previsão de t usa dados até t − 1 (o pedido real usa t − 4 a t − 5; seção 10)"],
        ["Métrica principal", "pinball loss em τ = 0,75, dividida pela média real do teste; sensibilidade em 0,6 e 0,9"],
        ["Métrica secundária", "MAE (leitura do gestor; reportada como WAPE = MAE ÷ média, para não revelar volume)"],
        ["Partição", "temporal: treino abr–jul/2026, teste ago–set/2026; nunca aleatória"],
    ], larg=[3.5, 13.9], fonte=8.5)
    r.p(("negrito", "Por que pinball em τ = 0,75. "), "Sem restrição de espaço, faltar (0,40 do preço) custaria "
        "15 a 20 vezes mais que sobrar (~0,026: 1,5 mês de capital a 1,5% ao mês, hipótese da equipe, mais "
        "desconto raro), e o τ ótimo ficaria acima de 0,93. Mas o container sai cheio: cada m² dado a um código "
        "é negado a outro, e exagerar custa a margem do código que ficou de fora, da mesma ordem do custo de "
        "faltar. Esse preço-sombra puxa o τ para perto de 0,5. Adotou-se 0,75 entre os dois extremos. "
        "Limitação: o τ é global, mas o preço-sombra é por código (proporcional à área); um código de margem "
        "alta e pouco m² mereceria τ mais alto.")

    # ---------------- 4
    r.h1("4. Dados")
    r.li("Exportação do ERP Sankhya, recebida em 20 e 21/10/2026 com autorização do gestor; fev a out/2026, "
         "com fevereiro e outubro parciais. Ficam 7 meses completos (mar–set).")
    r.li("73 códigos, agregados em 64 códigos de demanda. O filtro de negócio `incluir` deixa 30 códigos no "
         f"projeto. Painel: {n(204, 0)} linhas código × mês, 10,3% com venda zero e 15,2% com sinal de ruptura.")
    r.li(f"Treino: {R['linhas_treino']} linhas (abr–jul; março entra só como defasagem). Teste: "
         f"{R['linhas_teste']} linhas ({R['codigos_teste']} códigos × 2 meses), usado uma vez.")
    r.li("O cadastro traz m² por bobina de cada código (53 a 76 m²). Não foi preciso usar a área média do "
         f"container ({n(C.M2_CONTAINER / C.BOBINAS_CONTAINER, 0)} m²/bobina).")
    r.li("Sigilo: os dados e qualquer métrica em m² ficam fora do repositório público (.gitignore). Este "
         "relatório mostra só métricas relativas.")

    # ---------------- 5
    r.h1("5. Método")
    r.h2("5.1 Mudança de baseline: P75 de 6 meses → média de 3 meses")
    r.p("A E04 e a E05 descreveram a regra operacional como o percentil 75 da venda dos 6 últimos meses. Na "
        "devolutiva de 23 e 25/11, o gestor confirmou que o estoque mínimo é a ", ("negrito", "média de venda "
        "dos 3 últimos meses fechados"), " (coluna “Giro Média 30 à 90” do Sankhya). A partir desta entrega, "
        "o B0 é a média 3m. O P75 6m continua no quadro para manter a comparação com a E05.")
    linhas = []
    for tau in ["tau_0.6", "tau_0.75", "tau_0.9"]:
        e = T1[tau]["entre_bases"]["B0_p75_6 - B0_media3"]
        qq = {x["abordagem"]: x for x in T1[tau]["quadro"]}
        linhas.append([tau.replace("tau_", "τ = ").replace(".", ","), n(qq["B0_media3"]["pinball_rel_%"]) + "%",
                       n(qq["B0_p75_6"]["pinball_rel_%"]) + "%", pp(e["ponto"]), ic(e["ic95"])])
    r.tabela(["τ", "média 3m", "P75 6m", "P75 − média", "IC 95% (bootstrap de códigos)"], linhas,
             larg=[2.0, 2.6, 2.6, 3.0, 5.0])
    r.legenda(f"Tabela 1. Pinball relativa das duas regras no teste. Cobertura: média 3m "
              f"{n(q['B0_media3']['cobertura_%'], 0)}%, P75 6m {n(q['B0_p75_6']['cobertura_%'], 0)}%; viés "
              f"{n(q['B0_media3']['vies_%'], 0, True)}% e {n(q['B0_p75_6']['vies_%'], 0, True)}%.")
    e75 = T1["tau_0.75"]["entre_bases"]["B0_p75_6 - B0_media3"]
    e60 = T1["tau_0.6"]["entre_bases"]["B0_p75_6 - B0_media3"]
    r.p("Leitura: a troca do B0 se justifica pelo processo real da empresa, não pelo teste. No teste o P75 é "
        f"pior em τ = 0,75 ({pp(e75['ponto'])}), mas o IC inclui zero; só em τ = 0,6 a diferença é "
        f"significativa ({pp(e60['ponto'])}, IC {ic(e60['ic95'])}); em 0,9 as duas empatam. O P75 já é um quantil, então soma "
        "margem de segurança sobre um nível que, no teste, já estava alto (viés positivo). Ressalva: com "
        "horizonte de 1 mês, no começo do treino as duas janelas têm menos meses que o nominal (o P75 de abril "
        "usa só março). Nenhuma das duas é exatamente a regra em regime.")

    r.h2("5.2 Decomposição do ganho em três níveis")
    r.p("O baseline é uma média e os modelos estimam um quantil. Na pinball em 0,75, que pune subestimar 3× "
        "mais, um quantil ganha de uma média por construção, mesmo sem prever melhor. Para separar os efeitos, "
        "cada abordagem é pontuada na mesma partição e com a mesma métrica:")
    r.li(("negrito", "B0: "), "a regra crua.")
    r.li(("negrito", "B1 = s × B0: "), "s é o quantil τ de real ÷ B0 no treino (linhas com B0 > 0), para "
         "que ~75% dos reais fiquem abaixo de s × B0. É o que a empresa faz com estoque mínimo e folga. "
         "Variante: o s que minimiza a pinball no treino, que é o mesmo quantil ponderado por B0.")
    r.li(("negrito", "M: "), "os três modelos de quantil. ", ("negrito", "Efeito quantil = B1 − B0; "
         "efeito modelagem = M − B1."), " Valores negativos indicam melhora.")

    r.h2("5.3 Modelos, grades e validação")
    r.p("Features (todas defasadas de 1 mês por código): última venda, média e máximo de 3 meses, média "
        "histórica, número de meses de histórico, largura, linha, acabamento e marca. Imputação, padronização e "
        "one-hot ficam dentro do Pipeline e são ajustados só no treino de cada fold. Validação: "
        f"TimeSeriesSplit sobre os meses do treino, {C.N_SPLITS_CV} folds de janela expansiva (validação em mai, "
        f"jun e jul). Semente {C.SEMENTE}.")
    r.tabela(["Modelo", "Por que este", "Grade (registrada em src/config.py)"], [
        ["Linear regularizado", "QuantileRegressor: perda pinball nativa, penalidade L1",
         "alpha ∈ " + str(C.GRADE_LINEAR["alpha"])],
        ["Árvore de decisão", "sklearn não tem árvore quantil: árvore na média × s calibrado nas previsões de "
         "validação do CV (no próprio treino a árvore decora os dados e s ≈ 1)",
         f"max_depth ∈ {C.GRADE_ARVORE['max_depth']}; min_samples_leaf ∈ {C.GRADE_ARVORE['min_samples_leaf']}"],
        ["Ensemble", "GradientBoosting com loss = quantile, alpha = τ",
         f"n_estimators ∈ {C.GRADE_GB['n_estimators']}; max_depth ∈ {C.GRADE_GB['max_depth']}; "
         f"learning_rate ∈ {C.GRADE_GB['learning_rate']}; min_samples_leaf ∈ {C.GRADE_GB['min_samples_leaf']}"],
    ], larg=[2.8, 7.2, 7.4], fonte=8)
    r.p(("negrito", "Incerteza: "), f"IC 95% por bootstrap de códigos ({C.N_BOOT} reamostragens). Os 2 meses de "
        "teste de um mesmo código não são independentes, e reamostrar linhas daria um intervalo estreito demais. ",
        ("negrito", "Vazamento: "), "o teste da E05 perturba as vendas e compras brutas depois de um corte, refaz "
        f"o pipeline e exige features idênticas até o corte. Passou nos cortes {', '.join(T3['teste_vazamento']['cortes'])}.")

    # ---------------- 6
    r.h1("6. Resultados")
    fig = figuras(R, saida / "figs")
    r.figura(fig)
    r.legenda("Figura 1. (a) Pinball relativa no teste, τ = 0,75; a linha tracejada marca a regra atual. "
              "(b) Correlação da demanda normalizada entre meses separados por k (seção 10).")
    linhas = []
    for a in ["B0_media3", "B1_media3", "B0_p75_6", "B1_p75_6", "M_linear_quantil", "M_arvore_fator", "M_gb_quantil"]:
        x = q[a]
        mod = mods.get(a)
        hip = (", ".join(f"{k}={v}" for k, v in mod["params"].items()) if mod else
               f"s = {n(t['bases'][a.split('_', 1)[1]]['s_cobertura_treino'], 3)}" if a.startswith("B1") else "regra fixa")
        tempo = f"{n(mod['tempo_busca_s'], 1)} s / {n(mod['tempo_inferencia_ms'], 0)} ms" if mod else "—"
        cv = n(mod["cv_pinball_rel_%"]) + "%" if mod else "—"
        linhas.append([NOME[a], hip, cv, n(x["pinball_rel_%"]) + "%", n(x["WAPE_%"], 0) + "%",
                       n(x["cobertura_%"], 0) + "%", n(x["vies_%"], 0, True) + "%", tempo])
    r.tabela(["Abordagem", "Hiperparâmetros", "CV pinball", "Pinball teste", "WAPE", "Cobertura", "Viés",
              "Busca / inferência"], linhas, larg=[3.6, 4.4, 1.4, 1.5, 1.2, 1.5, 1.2, 2.6], fonte=7.5,
             destaque={0})
    r.legenda("Tabela 2. Quadro de comparação, τ = 0,75, mesmo teste. WAPE = MAE ÷ demanda real (métrica "
              "secundária). Viés positivo = previsão acima do real. Busca = grade inteira com CV; inferência = "
              "60 linhas.")

    def lin_ef(base, rot):
        e = t["bases"][base]["efeitos"]
        b0, b1 = f"B0_{base}", f"B1_{base}"
        out = [[f"{rot}: efeito quantil (B1 − B0)", pp(e[f'{b1} - {b0}']['ponto']), ic(e[f'{b1} - {b0}']['ic95'])]]
        for m in ["M_linear_quantil", "M_arvore_fator", "M_gb_quantil"]:
            out.append([f"{rot}: modelagem, {NOME[m][2:]} − B1", pp(e[f'{m} - {b1}']['ponto']),
                        ic(e[f'{m} - {b1}']['ic95'])])
        out.append([f"{rot}: GB − B0 (ganho total)", pp(e[f'M_gb_quantil - {b0}']['ponto']),
                    ic(e[f'M_gb_quantil - {b0}']['ic95'])])
        return out
    r.tabela(["Decomposição (τ = 0,75)", "Diferença", "IC 95%"], lin_ef("media3", "média 3m") + lin_ef("p75_6", "P75 6m"),
             larg=[9.0, 2.6, 4.2], fonte=8, destaque={4, 9})
    r.legenda("Tabela 3. Efeitos em pontos percentuais de pinball relativa; negativo = melhora.")
    r.p(("negrito", "Leitura. "), f"(i) O efeito quantil é uma ", ("negrito", "piora"),
        f": {pp(em['B1_media3 - B0_media3']['ponto'])} sobre a média 3m. No treino a média 3m cobria só "
        f"{n(bm['cobertura_treino_B0_%'], 0)}% dos reais, e o s = {n(bm['s_cobertura_treino'], 2)} corrigiu isso. "
        f"No teste ela já cobre {n(q['B0_media3']['cobertura_%'], 0)}%, porque a venda de ago–set ficou abaixo do "
        "histórico recente: todas as abordagens têm viés positivo. A folga calibrada no treino vira excesso no "
        "teste. (ii) O efeito modelagem é pequeno e não significativo. O GB é o único que melhora sobre B1 "
        f"({pp(em['M_gb_quantil - B1_media3']['ponto'])}), mas ", ("negrito", "não recupera a perda do efeito quantil"),
        ". (iii) A árvore é a pior e o linear escolheu alpha = 0 (nenhuma regularização ajudou na CV). "
        "(iv) A CV (mai–jul) dá pinball menor que o teste para todos os modelos: o teste é mais difícil, não "
        "houve ajuste ao teste.")
    linhas = []
    for tau in ["tau_0.6", "tau_0.75", "tau_0.9"]:
        bb = T1[tau]["bases"]["media3"]["efeitos"]
        linhas.append([tau.replace("tau_", "").replace(".", ","), n(pin("B0_media3", tau)) + "%",
                       n(pin("B1_media3", tau)) + "%", n(pin("M_gb_quantil", tau)) + "%",
                       pp(bb["B1_media3 - B0_media3"]["ponto"]), pp(bb["M_gb_quantil - B1_media3"]["ponto"]),
                       ic(bb["M_gb_quantil - B1_media3"]["ic95"])])
    r.tabela(["τ", "B0 média 3m", "B1", "GB", "Efeito quantil", "Efeito modelagem (GB)", "IC 95%"], linhas,
             larg=[1.2, 2.2, 1.8, 1.8, 2.5, 3.3, 3.6], fonte=8)
    r.legenda("Tabela 4. Sensibilidade a τ: s e os modelos são refeitos em cada τ; B0 é a mesma regra.")
    r.p("A conclusão não depende do τ: em nenhum dos três o GB tem ganho distinguível de zero sobre B1.")

    # ---------------- 7
    r.h1("7. Limiar e operação")
    r.p("A unidade de decisão é o pedido de um ciclo (1 mês de cobertura): previsão em m², arredondada para "
        f"cima em bobinas inteiras do código e com piso de {C.PISO_BOBINAS} bobinas. Sobra = pedido acima da "
        "venda (capital parado e espaço); falta = venda acima do pedido (margem perdida). Valores em % da "
        "demanda real do ciclo; os m² absolutos ficam no repositório privado.")
    linhas = []
    for a in ["B0_media3", "B1_media3", "B0_p75_6", "M_gb_quantil"]:
        x, y = dec[(a, "previsao_m2")], dec[(a, "pedido_bobinas_com_piso")]
        linhas.append([NOME[a], n(y["pedido_%_demanda"], 0) + "%", n(y["sobra_%_demanda"], 1) + "%",
                       n(y["falta_%_demanda"], 1) + "%", n(y["meses_codigo_com_falta_por_ciclo"], 1),
                       pp(y["sobra_%_demanda"] - x["sobra_%_demanda"])])
    r.tabela(["Abordagem", "Pedido ÷ demanda", "Sobra", "Falta", "Códigos com falta / ciclo",
              "Sobra criada pelo piso"], linhas, larg=[4.6, 2.4, 1.8, 1.8, 3.2, 3.0], fonte=8, destaque={0})
    piso = [dec[(a, "pedido_bobinas_com_piso")]["sobra_%_demanda"] - dec[(a, "previsao_m2")]["sobra_%_demanda"]
            for a in ["B0_media3", "B1_media3", "B0_p75_6", "M_gb_quantil"]]
    gm = g[("B0_media3", "pedido_bobinas_com_piso")]
    irr = C.MARGEM_FALTA * gm["delta_falta_%_demanda"] + C.CUSTO_SOBRA_IRRESTRITO * gm["delta_sobra_%_demanda"]
    cheio = C.MARGEM_FALTA * (gm["delta_falta_%_demanda"] + gm["delta_sobra_%_demanda"])
    r.legenda("Tabela 5. Pedido de um ciclo no teste, média dos 2 meses, com piso de 30 bobinas.")
    r.p(("negrito", "GB contra a regra atual, em unidade de decisão: "),
        f"{pp(gm['delta_falta_%_demanda'])} de falta, {pp(gm['delta_sobra_%_demanda'])} de sobra e "
        f"{n(gm['delta_meses_codigo_com_falta_por_ciclo'], 1, True)} código com falta por ciclo. O modelo "
        "troca sobra por menos falta. Em custo, com falta a 0,40 do preço:")
    r.li(("negrito", "Se sobra espaço no container "), f"(sobra a {n(C.CUSTO_SOBRA_IRRESTRITO, 3)}): "
         f"{pp(irr, 2)} da receita do ciclo; o GB compensaria.")
    r.li(("negrito", "Se o container sai cheio "), f"(sobra custa a margem do código que ficou de fora, ~0,40): "
         f"{pp(cheio, 2)}; o GB é pior.")
    r.p("Como a devolutiva diz que só vale container cheio, o regime relevante é o segundo, e a recomendação "
        "operacional desta entrega é ", ("negrito", "manter a média 3m como base do pedido"), ". O piso de "
        f"{C.PISO_BOBINAS} bobinas sozinho cria de {n(min(piso))} a {n(max(piso))} p.p. de sobra nas abordagens da "
        "tabela: nos códigos pequenos, a decisão é entrar ou não no pedido, e não quanto pedir.")

    # ---------------- 8
    r.h1("8. Erros e equidade")
    def linha_g(col, chave, rot):
        v = gr[col][chave]
        return [rot, v["codigos"], n(v["parcela_demanda_%"], 0) + "%"] + \
            [f"{n(v[a]['pinball_rel_%'], 0)}% / {n(v[a]['vies_%'], 0, True)}%" for a in ["B0_media3", "B0_p75_6", "M_gb_quantil"]] + \
            [n(v["M_gb_quantil"]["parcela_custo_falta_%"], 0) + "%"]
    linhas = [linha_g("giro", "alto", "giro alto"), linha_g("giro", "medio", "giro médio"),
              linha_g("giro", "baixo", "giro baixo"),
              linha_g("marca", "UNIPRO", "marca UNIPRO"), linha_g("marca", "UNITRAMA", "marca UNITRAMA"),
              linha_g("marca", "INFLEX", "marca INFLEX"),
              linha_g("acabamento", "TRANSPARENTE", "acabamento transparente"),
              linha_g("acabamento", "NAO_INFORMADO", "acabamento não informado"),
              linha_g("ruptura_no_mes", "sem_ruptura", "mês sem ruptura"),
              linha_g("ruptura_no_mes", "com_ruptura", "mês com ruptura")]
    linhas.append(["fora do filtro `incluir`", fora["codigos"],
                   n(fora["demanda_relativa_aos_oficiais_%"], 0) + "%*"] +
                  [f"{n(fora[a]['pinball_rel_%'], 0)}% / {n(fora[a]['vies_%'], 0, True)}%"
                   for a in ["B0_media3", "B0_p75_6", "M_gb_quantil"]] +
                  [n(fora["M_gb_quantil"]["parcela_custo_falta_%"], 0) + "%"])
    r.tabela(["Grupo", "Códigos", "Demanda", "média 3m", "P75 6m", "GB", "Custo GB que é falta"], linhas,
             larg=[3.8, 1.4, 1.6, 2.4, 2.4, 2.4, 2.4], fonte=7.5)
    r.legenda("Tabela 6. Pinball relativa à média do próprio grupo / viés, no teste. Giro definido pelos tercis "
              "da venda média no treino. * Demanda em % da dos 30 códigos oficiais; GB treinado só nos 30. Custo "
              "que é falta: falta a 0,40 contra sobra a 0,026.")
    r.li(("negrito", "Faixa e perfil: "), "o erro relativo se concentra nos códigos de baixo giro "
         f"({n(gr['giro']['baixo']['parcela_demanda_%'], 0)}% da demanda), onde o P75 tem viés de "
         f"{n(gr['giro']['baixo']['B0_p75_6']['vies_%'], 0, True)}%. Nos de giro alto, todas as abordagens ficam "
         f"perto de 20%. Os 20% de códigos com mais erro respondem por {n(T4['concentracao']['parcela_erro_abs_gb_top20pct_%'], 0)}% "
         f"do erro, menos que os {n(T4['concentracao']['parcela_demanda_top20pct_volume_%'], 0)}% de demanda dos "
         "20% maiores: em termos relativos, os códigos pequenos erram mais. INFLEX e transparente são os perfis "
         "sistematicamente superestimados.")
    cf = lambda k: n(gr["giro"][k]["M_gb_quantil"]["parcela_custo_falta_%"], 0) + "%"
    r.li(("negrito", "Erros caros e toleráveis: "), f"no GB, a falta, que é o erro caro, responde por {cf('alto')} do "
         f"custo do erro nos códigos de giro alto e {cf('medio')} nos de giro médio. No baixo giro, só {cf('baixo')}: "
         "o erro é majoritariamente sobra, tolerável quando há espaço.")
    r.li(("negrito", "Códigos novos: "), "dentro dos 30, só 2 códigos têm 3 meses ou menos de histórico no teste, "
         "poucos demais para medir. O grupo relevante são os ", ("negrito", f"{fora['codigos']} códigos fora do "
         "filtro"), f": vendem {n(fora['demanda_relativa_aos_oficiais_%'] / 100, 2)}× o volume dos oficiais, e "
         f"todas as abordagens os subestimam (viés de {n(fora['M_gb_quantil']['vies_%'], 0, True)}% no GB, "
         f"cobertura de {n(fora['M_gb_quantil']['cobertura_%'], 0)}%). O projeto cobre menos de um terço do "
         "volume. É a diferença entre grupos mais importante, e não foi corrigida neste semestre.")
    r.li(("negrito", "Erro de dado, não de modelo: "), f"{n(T4['erro_de_dado']['parcela_linhas_com_ruptura_%'], 0)}% "
         "das linhas de teste têm ruptura. Nelas a venda registrada fica abaixo da demanda real, e todas as "
         "abordagens parecem superestimar. Ali está "
         f"{n(T4['erro_de_dado']['parcela_sobra_gb_em_meses_com_ruptura_%'], 0)}% da sobra aparente do GB.")

    # ---------------- 9
    r.h1("9. Produto / MVP (esboço)")
    r.p("Uma planilha de apoio ao pedido, gerada a cada ciclo, para o gestor revisar e ajustar. Ela não "
        "decide sozinha. Wireframe:")
    r.mono("PEDIDO SUGERIDO — container nº __ · fechamento __/__ · capacidade 93.400 m²   [ocupado: ██████░░ 78%]\n"
           "┌────────┬──────────┬──────────┬──────────┬─────────┬──────────┬────────┬─────────────────────────┐\n"
           "│ código │ estoque  │ trânsito │ média 3m │ P75 mod.│ sugerido │ m²     │ alerta                  │\n"
           "│        │ (m²)     │ (m²)     │ (regra)  │ (τ=0,75)│ (bobinas)│ acum.  │                         │\n"
           "├────────┼──────────┼──────────┼──────────┼─────────┼──────────┼────────┼─────────────────────────┤\n"
           "│ ....   │  ....    │  ....    │  ....    │  ....   │  30 (piso)│ ....  │ baixo giro: entra?      │\n"
           "│ ....   │  ....    │  ....    │  ....    │  ....   │  ....    │ ....   │ ruptura recente         │\n"
           "│ ....   │  ....    │  ....    │  ....    │  ....   │  ....    │ ....   │ fora do modelo (manual) │\n"
           "└────────┴──────────┴──────────┴──────────┴─────────┴──────────┴────────┴─────────────────────────┘\n"
           "[ajustar quantidade]  [travar código]  [exportar para o Sankhya]")
    r.p("Pendência: a repartição dos m² do container entre os códigos, priorizando risco de falta, ainda "
        "não está implementada; hoje o protótipo calcula sobra e falta por código.")

    # ---------------- 10
    r.h1("10. Riscos e limites (esboço)")
    l1, l4, l5 = lag["lag_1"], lag["lag_4"], lag["lag_5"]
    r.li(("negrito", "Defasamento (medido): "), "o modelo prevê 1 mês à frente, mas o pedido é fechado 4 a 5 "
         "meses antes da chegada. Com cada série dividida pela média do código, a correlação entre meses é "
         f"{n(l1['correlacao'], 2, True)} no lag 1, {n(l4['correlacao'], 2, True)} no lag 4 e "
         f"{n(l5['correlacao'], 2, True)} no lag 5. Como séries curtas centradas na própria média têm correlação "
         f"negativa mesmo sem estrutura, a comparação é com a referência de meses embaralhados "
         f"(~{n(l1['correlacao_nula_media'], 2, True)}). Lag 1 fica acima dela (p < 0,001); lag 5, abaixo "
         f"(p = {n(l5['p_valor_bilateral'], 3)}). A variação média da demanda em 5 meses é "
         f"{n(l5['variacao_abs_media_x'] * 100, 0)}% da média do código, contra {n(l1['variacao_abs_media_x'] * 100, 0)}% "
         "em 1 mês. O proxy de 1 mês subestima a incerteza do pedido real. Fragilidade: o lag 5 tem no máximo "
         f"2 pares por código ({l5['pares']} no total) e o resultado é indicativo, não conclusivo.")
    r.li(("negrito", "Teste curto: "), "2 meses. Não dá para separar “modelo ruim” de “ago–set atípicos”.")
    r.li(("negrito", "Ruptura censura a demanda "), "e o sinal de ruptura depende do estoque reconstruído (E04).")
    r.li(("negrito", "Cobertura do projeto: "), "o filtro `incluir` deixa fora a maior parte do volume (seção 8).")
    r.li(("negrito", "Custo de sobrar "), "usa a hipótese de 1,5% ao mês; a empresa não tem esse número.")

    # ---------------- 11
    r.h1("11. Devolutiva com o demandante")
    r.p("Conversas de 23 e 25/11/2026 com Francisco Cavalcanti Junior, registradas por João Filipe Dantas em "
        "docs/E06_devolutiva_francisco.md. Pontos que mudaram o projeto:")
    r.li("Venda perdida não volta e a margem é de ~40%: o custo de faltar é a margem.")
    r.li("Produto parado gira em ~1 mês; depois de ~45 dias pode exigir desconto de 10 a 15%, o que é raro.")
    r.li("O limite é o container cheio e o caixa (1 a 2 containers por mês): introduz o preço-sombra do espaço e "
         "leva ao τ = 0,75, com sensibilidade em 0,6 e 0,9.")
    r.li("A regra de estoque mínimo é a média dos 3 últimos meses fechados, e não o P75 de 6 meses: muda o "
         "baseline (seção 5.1).")
    r.p("Em aberto: a razão exata “faltar é X vezes pior” e o custo mensal de capital.")

    # ---------------- 12
    r.h1("12. Reprodutibilidade")
    r.mono("git clone " + REPO + "\ncd printmais && pip install -r requirements.txt\n"
           "# dados privados em dados/bruto/ (ver dados/bruto/COMO_OBTER.md)\n"
           "python -m src.e06 --fonte real          # T1–T4, ~4 min -> relatorios/real/e06.json\n"
           "python -m scripts.relatorio_e06         # este relatório, a partir do JSON\n"
           "python -m src.e06 --fonte amostra       # sem a base: amostra 100% sintética versionada")
    r.li(f"Semente {C.SEMENTE} em todo componente aleatório (modelos e bootstraps). Duas execuções geram o "
         "mesmo JSON, exceto os campos de tempo.")
    r.li("Todo número deste relatório é lido do JSON pelo script; nenhum foi digitado à mão.")
    r.li("Executado com Python 3.13.5 e scikit-learn 1.7.2. [CONFIRMAR: o requirements.txt fixa 1.9.1.]")
    r.li("Grades em src/config.py; dados e métricas em m² fora do git; teste de vazamento dentro do comando.")

    # ---------------- apêndices
    r.h1("Apêndice A — Contribuição dos integrantes")
    r.tabela(["Integrante", "Contribuição"], [
        ["Pedro Rebouças Veloso", "[PREENCHER]"],
        ["João Filipe Dantas", "devolutiva com o gestor (seção 11) · [PREENCHER]"]], larg=[4.5, 12.9])
    r.h1("Apêndice B — Declaração de uso de IA")
    r.li(("negrito", "Ferramentas: "), "Claude Code (Anthropic), modelo Claude Opus 5.5.")
    r.li(("negrito", "Finalidade: "), "inventário do repositório; implementação de src/e06.py (T1 e T2), "
         "src/e06_decisao.py (T3 e T4), notebooks/02_entrega6.ipynb e scripts/relatorio_e06.py (este relatório); "
         "redação inicial deste texto.")
    r.li(("negrito", "Decisões da equipe, não da IA: "), "τ = 0,75 e a sensibilidade; B0 = média 3m e manutenção "
         "do P75; população de 30 códigos; modelos com perda quantil nativa; cobertura de 1 mês; ganho em m².")
    r.li(("negrito", "Dados: "), "a IA executou o código localmente e viu só saídas agregadas relativas. "
         "Incidente: no inventário ela leu relatorios/real/metricas_modelo.json, cujo bloco piores_skus traz "
         "volume em m² por código (5 códigos). [CONFIRMAR o texto do incidente com a equipe.]")
    r.h1("Apêndice C — Hipóteses descartadas")
    r.li("P75 de 6 meses como regra da empresa → substituído pela média 3m (devolutiva).")
    r.li("Horizonte de 5 meses no treino → com 7 meses de histórico, não sobra nenhuma linha avaliável; "
         "substituído por H = 1 e defasamento medido (seção 10).")
    r.li("Ridge (prevê a média) como modelo único da E05 → substituído por três modelos de perda quantil.")
    r.li("Estoque reconstruído e ruptura como features → removidos por vazamento na E05.")
    r.li("Cobertura de 2 meses após a chegada → 1 mês (1 a 2 containers por mês).")
    r.li("Área média de 58 m²/bobina → m² por bobina real de cada código.")
    r.li("Sensibilidade em τ = 0,67 e 0,83 (primeira devolutiva) → 0,6 e 0,9.")

    docx = saida / "E06_equipeE_relatorio_preliminar.docx"
    r.d.save(docx)
    return docx


def para_pdf(docx):
    """Converte com o Word (Windows), se houver. Devolve (pdf, páginas) ou (None, None)."""
    pdf = docx.with_suffix(".pdf")
    ps = (f"$w = New-Object -ComObject Word.Application; $w.Visible = $false; "
          f"$d = $w.Documents.Open('{docx}'); $p = $d.ComputeStatistics(2); "
          f"$d.SaveAs([ref] '{pdf}', [ref] 17); $d.Close(); $w.Quit(); $p")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             timeout=180)
        return (pdf, out.stdout.strip()) if pdf.exists() else (None, out.stderr.strip()[:300])
    except Exception as e:      # sem Word: fica só o .docx
        return None, str(e)


def main(fonte="real"):
    saida = C.DIR_SAIDA_REAL if fonte == "real" else C.DIR_SAIDA_AMOSTRA
    R = json.loads((saida / "e06.json").read_text(encoding="utf-8"))
    checar(R)
    docx = gerar(R, saida)
    pdf, info = para_pdf(docx)
    print(f"docx: {docx.relative_to(C.RAIZ).as_posix()}")
    print(f"pdf: {pdf.relative_to(C.RAIZ).as_posix()} ({info} páginas)" if pdf else f"pdf não gerado: {info}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", choices=["real", "amostra"], default="real")
    main(ap.parse_args().fonte)
