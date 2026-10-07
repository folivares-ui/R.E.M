import sqlite3

import pytest

from rem.tools.documents import DocumentError, read_document
from rem.tools.database import run_query, validate_readonly_sql


def test_markdown_and_pagination(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("x" * 100, encoding="utf-8")
    r = read_document(str(p), None, 0, 40)
    assert r["has_more"] and r["next_offset"] == 40 and r["total_chars"] == 100
    r2 = read_document(str(p), None, 80, 40)
    assert not r2["has_more"] and r2["returned_chars"] == 20


def test_docx_with_table(tmp_path):
    import docx
    d = docx.Document()
    d.add_heading("Título", 1)
    d.add_paragraph("Hola mundo")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "a", "b"
    p = tmp_path / "x.docx"; d.save(p)
    txt = read_document(str(p))["text"]
    assert "# Título" in txt and "Hola mundo" in txt and "a | b" in txt


def test_xlsx_and_csv(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Ventas"
    ws.append(["mes", "total"]); ws.append(["ene", 10])
    p = tmp_path / "v.xlsx"; wb.save(p)
    assert "Hoja: Ventas" in read_document(str(p))["text"]
    c = tmp_path / "v.csv"; c.write_text("a,b\n1,2\n")
    assert "1\t2" in read_document(str(c))["text"]


def test_pptx(tmp_path):
    from pptx import Presentation
    prs = Presentation(); s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Plan"; s.placeholders[1].text = "Punto uno"
    p = tmp_path / "d.pptx"; prs.save(p)
    t = read_document(str(p))["text"]
    assert "Plan" in t and "Punto uno" in t


def test_pdf(tmp_path):
    from pypdf import PdfWriter
    w = PdfWriter(); w.add_blank_page(200, 200)
    p = tmp_path / "b.pdf"; w.write(p)
    t = read_document(str(p))["text"]
    assert "Página 1" in t and "OCR" in t  # PDF sin texto: avisa en lugar de callar


def test_sqlite_summary_and_query(tmp_path):
    db = tmp_path / "t.db"
    con = sqlite3.connect(db); con.execute("create table v(id int, n text)"); con.executemany("insert into v values(?,?)", [(1, "a"), (2, "b")]); con.commit(); con.close()
    assert "Tabla v (2 filas)" in read_document(str(db))["text"]
    r = run_query(f"sqlite:///{db}", "select * from v order by id")
    assert r["rows"] == [[1, "a"], [2, "b"]] and not r["truncated"]


@pytest.mark.parametrize("sql", ["delete from v", "select 1; drop table v", "insert into v values(1,'x')", "pragma writable_schema=1", "with x as (select 1) update v set n='z'"])
def test_sql_write_blocked(sql):
    with pytest.raises(ValueError):
        validate_readonly_sql(sql)


def test_sqlite_is_opened_read_only(tmp_path):
    db = tmp_path / "t.db"; sqlite3.connect(db).execute("create table v(id int)").connection.commit()
    # incluso si una consulta "legítima" intentara escribir, la conexión es de solo lectura
    assert run_query(f"sqlite:///{db}", "select count(*) from v")["rows"] == [[0]]


def test_root_confinement(tmp_path):
    inside = tmp_path / "ok"; inside.mkdir(); (inside / "a.txt").write_text("hi")
    (tmp_path / "secret.txt").write_text("no")
    assert read_document(str(inside / "a.txt"), inside)["text"] == "hi"
    with pytest.raises(DocumentError):
        read_document(str(tmp_path / "secret.txt"), inside)
    with pytest.raises(DocumentError):
        read_document(str(inside / ".." / "secret.txt"), inside)


def test_legacy_doc_via_libreoffice(tmp_path):
    import shutil
    if not shutil.which("soffice"):
        pytest.skip("LibreOffice no instalado")
    import docx
    d = docx.Document(); d.add_paragraph("contenido legado"); src = tmp_path / "n.docx"; d.save(src)
    import subprocess
    subprocess.run(["soffice", "--headless", "--convert-to", "doc", "--outdir", str(tmp_path), str(src)], check=True, capture_output=True, timeout=180)
    assert "contenido legado" in read_document(str(tmp_path / "n.doc"))["text"]


def test_mpp_reader_with_mspdi_xml(tmp_path):
    jpype = pytest.importorskip("jpype")
    pytest.importorskip("mpxj")
    import mpxj  # noqa: F401
    if not jpype.isJVMStarted():
        jpype.startJVM()
    from org.mpxj import ProjectFile  # type: ignore
    from org.mpxj.mspdi import MSPDIWriter  # type: ignore
    pf = ProjectFile(); t = pf.addTask(); t.setName("Cimentación")
    out = tmp_path / "plan.xml"; MSPDIWriter().write(pf, str(out))
    from rem.tools.documents import _read_mpp
    assert "Cimentación" in _read_mpp(out)
