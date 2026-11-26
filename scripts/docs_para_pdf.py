"""Compacta a tipografia do .docx exportado do Claude Docs e gera o PDF pelo Word.

Uso: python compactar.py <entrada.docx> <saida.pdf>
Só muda forma (fonte, margens, espaçamento, largura das figuras); nenhum texto é tocado.
"""
import subprocess
import sys
from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

TEXTO, TAB, CODIGO = Pt(9.5), Pt(8), Pt(7.5)


def fonte_runs(par, tam, nome=None):
    for r in par.runs:
        r.font.size = tam
        if nome:
            r.font.name = nome
            r._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), nome)


def eh_codigo(par):
    fontes = {r.font.name for r in par.runs if r.text.strip()}
    return bool(fontes) and all(f and ("Mono" in f or "Courier" in f or "Consol" in f) for f in fontes)


def main(entrada, saida_pdf):
    d = docx.Document(entrada)
    for s in d.sections:
        s.page_height, s.page_width = Cm(29.7), Cm(21.0)
        s.left_margin = s.right_margin = Cm(1.8)
        s.top_margin = s.bottom_margin = Cm(1.5)
    larg = d.sections[0].page_width - d.sections[0].left_margin - d.sections[0].right_margin

    if "Code" in [st.name for st in d.styles]:      # blocos de código do Docs: fonte vem do estilo
        d.styles["Code"].font.size = Pt(7)
    for par in d.paragraphs:
        pf = par.paragraph_format
        nome = par.style.name if par.style is not None else ""
        if nome.startswith("Heading") or nome.startswith("Title"):
            nivel = {"Title": 15, "Heading 1": 15, "Heading 2": 12.5, "Heading 3": 10.5}.get(nome, 10.5)
            fonte_runs(par, Pt(nivel))
            pf.space_before, pf.space_after = Pt(7), Pt(3)
        elif eh_codigo(par) or (par.style is not None and par.style.name == "Code"):
            fonte_runs(par, Pt(7))
            pf.space_before, pf.space_after, pf.line_spacing = Pt(0), Pt(0), 1.0
        else:
            fonte_runs(par, TEXTO)
            pf.space_before, pf.space_after, pf.line_spacing = Pt(0), Pt(3), 1.05

    for t in d.tables:
        for row in t.rows:
            for cel in row.cells:
                for par in cel.paragraphs:
                    fonte_runs(par, TAB)
                    pf = par.paragraph_format
                    pf.space_before, pf.space_after, pf.line_spacing = Pt(0), Pt(0), 1.0

    for shp in d.inline_shapes:          # figuras: no máximo 16 cm, proporção mantida
        alvo = min(Cm(16), larg)
        if shp.width > alvo:
            shp.height = int(shp.height * alvo / shp.width)
            shp.width = alvo

    tmp = Path(saida_pdf).with_suffix(".docx")
    d.save(tmp)
    ps = (f"$w = New-Object -ComObject Word.Application; $w.Visible = $false; "
          f"$d = $w.Documents.Open('{tmp.resolve()}'); $p = $d.ComputeStatistics(2); "
          f"$d.SaveAs([ref] '{Path(saida_pdf).resolve()}', [ref] 17); $d.Close(); $w.Quit(); $p")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=240)
    print("páginas:", out.stdout.strip() or out.stderr.strip()[:300])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
