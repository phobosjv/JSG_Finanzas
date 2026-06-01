"""
Genera manual-importacion-csv.pdf.
Ejecutar desde la raiz del proyecto:
  python gen_manual_csv.py
"""
from fpdf import FPDF

OUTPUT = "frontend/public/manual-importacion-csv.pdf"
TITLE  = "JSG Soft. - Guia de importacion CSV / CSV Import Guide"


class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 7, TITLE, align="R")
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, f"JSG Soft.  |  Pag. {self.page_no()}", align="C")

    def h1(self, text, lang="es"):
        color = (20, 80, 160) if lang == "es" else (0, 110, 60)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*color)
        self.cell(0, 9, text)
        self.ln(2)
        self.set_draw_color(*color)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

    def h2(self, text):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(60, 60, 60)
        self.cell(0, 7, text)
        self.ln(5)

    def body(self, text, indent=0):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        self.set_x(self.l_margin + indent)
        self.multi_cell(self.w - self.l_margin - self.r_margin - indent, 5, text)

    def gap(self, h=3):
        self.ln(h)

    def table_row(self, col1, col2, col3, col4, header=False):
        W = [28, 30, 45, 65]
        if header:
            self.set_font("Helvetica", "B", 9)
            self.set_fill_color(220, 230, 245)
            self.set_text_color(30, 30, 30)
        else:
            self.set_font("Helvetica", "", 9)
            self.set_fill_color(248, 248, 248)
            self.set_text_color(40, 40, 40)
        for text, w in zip([col1, col2, col3, col4], W):
            self.cell(w, 6, text, border=1, fill=True)
        self.ln()


def build_pdf(path: str) -> None:
    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(18, 18, 18)

    # =========================================================================
    #  PORTADA
    # =========================================================================
    pdf.add_page()
    pdf.ln(24)
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(20, 80, 160)
    pdf.cell(0, 14, "JSG Soft.", align="C")
    pdf.ln(12)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 9, "Guia de importacion CSV", align="C")
    pdf.ln(7)
    pdf.set_font("Helvetica", "", 13)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 7, "CSV Import Guide", align="C")
    pdf.ln(14)
    pdf.set_draw_color(180, 180, 180)
    pdf.set_line_width(0.4)
    pdf.line(40, pdf.get_y(), pdf.w - 40, pdf.get_y())
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 7, "Importacion masiva de compras, ventas y dividendos", align="C")
    pdf.ln(5)
    pdf.cell(0, 7, "Bulk import of buys, sells and dividends", align="C")

    # =========================================================================
    #  ESPANOL
    # =========================================================================
    pdf.add_page()
    pdf.h1("ESPANOL", lang="es")

    # --- Que es ---
    pdf.h2("Que es la importacion CSV")
    pdf.body(
        "La importacion CSV permite registrar de una sola vez todas tus compras, "
        "ventas y dividendos subiendo un fichero de texto delimitado por comas. "
        "El proceso es completamente seguro: se puede ejecutar varias veces con el "
        "mismo fichero sin crear registros duplicados (operacion idempotente)."
    )
    pdf.gap(6)

    # --- Proceso ---
    pdf.h2("Como funciona: pasos")
    steps_es = [
        "1. En la seccion Utilidades, haz clic en 'Seleccionar CSV'.",
        "2. Elige el fichero desde tu ordenador o movil.",
        "3. Revisa la vista previa: la tabla muestra todas las filas leidas.",
        "   Las filas con campos obligatorios vacios aparecen resaltadas en rojo.",
        "4. Si todo es correcto, haz clic en 'Importar (N filas)'.",
        "5. El sistema muestra el resultado: filas importadas, omitidas y errores.",
    ]
    for s in steps_es:
        pdf.body(s, indent=3)
        pdf.gap(1)
    pdf.gap(6)

    # --- Tickers ---
    pdf.h2("Identificacion del valor: ticker Yahoo Finance")
    pdf.body(
        "Cada fila del CSV identifica la accion mediante el campo 'ticker', que debe "
        "coincidir exactamente con el Yahoo Ticker registrado en el catalogo de valores "
        "de la aplicacion. Ejemplos: SAN.MC (Santander), BBVA.MC (BBVA), AAPL (Apple)."
    )
    pdf.gap(2)
    pdf.body(
        "IMPORTANTE: Si el ticker no existe en el catalogo, la fila se rechaza con "
        "un mensaje de error pero el resto del fichero se sigue procesando con normalidad. "
        "El administrador debe dar de alta el valor en el catalogo antes de importar."
    )
    pdf.gap(6)

    # --- Estructura columnas ---
    pdf.h2("Estructura del CSV: columnas")
    pdf.body("La primera fila debe ser la cabecera con estos nombres exactos:")
    pdf.gap(3)
    pdf.table_row("Columna", "Requerido", "Tipo / Valores", "Descripcion", header=True)
    cols_es = [
        ("type",            "Si",       "buy / sell / dividend",     "Tipo de operacion"),
        ("ticker",          "Si",       "texto",                     "Yahoo Ticker (en mayusculas)"),
        ("date",            "Si",       "YYYY-MM-DD",                "Fecha de la operacion"),
        ("shares",          "Si",       "numero > 0",                "Acciones (compra/venta) o acciones en fecha (dividendo)"),
        ("price",           "buy/sell", "numero > 0",                "Precio por accion (solo compra/venta)"),
        ("gross_per_share", "dividend", "numero > 0",                "Dividendo bruto por accion"),
        ("gross_amount",    "No",       "numero > 0",                "Importe bruto total (se calcula si se omite)"),
        ("fee",             "No",       "numero >= 0",               "Comision de la operacion (defecto: 0)"),
        ("withholding_tax", "No",       "numero >= 0",               "Retencion fiscal del dividendo (defecto: 0)"),
        ("currency",        "No",       "EUR / USD",                 "Divisa (defecto: EUR)"),
        ("exchange_rate",   "No",       "numero > 0",                "Tipo EUR/USD del BCE (obligatorio si USD, != 1)"),
    ]
    for row in cols_es:
        pdf.table_row(*row)
    pdf.gap(6)

    # --- Reglas por tipo ---
    pdf.h2("Reglas segun tipo de operacion")
    rules_es = [
        ("buy / sell",  "price es obligatorio. fee y exchange_rate son opcionales."),
        ("dividend",    "gross_per_share es obligatorio. gross_amount es opcional: si se "
                        "omite se calcula como shares x gross_per_share. withholding_tax "
                        "recoge la retencion aplicada por el broker."),
        ("USD",         "Si currency='USD', exchange_rate debe indicar el tipo de cambio "
                        "EUR/USD del BCE en la fecha de la operacion (nunca 1). "
                        "Si currency='EUR', exchange_rate debe ser 1 o dejarse vacio."),
    ]
    for tipo, desc in rules_es:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(20, 80, 160)
        pdf.cell(0, 6, tipo)
        pdf.ln(4)
        pdf.body(desc, indent=5)
        pdf.gap(3)
    pdf.gap(4)

    # --- Deduplicacion ---
    pdf.h2("Deduplicacion (importacion idempotente)")
    pdf.body(
        "El sistema detecta operaciones duplicadas usando estos criterios:"
    )
    pdf.gap(2)
    pdf.body("  Compra/venta: misma fecha + tipo + acciones + precio + comision.", indent=3)
    pdf.body("  Dividendo:    misma fecha + importe bruto total.", indent=3)
    pdf.gap(2)
    pdf.body(
        "Si una fila ya existe en la cartera con esos mismos valores, se omite "
        "silenciosamente (se cuenta como 'omitida', no como error). Esto permite "
        "reimportar el mismo fichero varias veces sin riesgo."
    )
    pdf.gap(6)

    # --- Ejemplo ---
    pdf.h2("Ejemplo de fichero CSV")
    pdf.set_font("Courier", "", 8)
    pdf.set_text_color(30, 30, 30)
    pdf.set_fill_color(240, 240, 240)
    example = (
        "type,ticker,date,shares,price,gross_per_share,gross_amount,fee,withholding_tax,currency,exchange_rate\n"
        "buy,SAN.MC,2023-01-15,100,3.25,,,0.50,,EUR,1\n"
        "sell,SAN.MC,2024-06-10,50,4.10,,,0.50,,EUR,1\n"
        "buy,AAPL,2023-03-20,10,152.50,,,1.00,,USD,1.0831\n"
        "dividend,SAN.MC,2023-07-05,100,0.025,2.50,,0.38,,EUR,1\n"
        "dividend,AAPL,2024-02-15,10,0.24,,,0.036,,USD,1.0920\n"
    )
    for line in example.strip().split("\n"):
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 5, line, border=0, fill=True)
        pdf.ln()
    pdf.gap(3)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.body(
        "Nota: en el dividendo de AAPL, gross_amount se omite; el sistema lo "
        "calcula como 10 x 0.24 = 2.40. En el de SAN.MC se indica explicitamente "
        "2.50 (valor real del broker, que puede diferir del calculado por redondeo)."
    )

    # =========================================================================
    #  ENGLISH
    # =========================================================================
    pdf.add_page()
    pdf.h1("ENGLISH", lang="en")

    # --- What is ---
    pdf.h2("What is CSV import")
    pdf.body(
        "CSV import lets you record all your buys, sells and dividends at once by "
        "uploading a comma-separated text file. The process is completely safe: it "
        "can be run multiple times with the same file without creating duplicate "
        "records (idempotent operation)."
    )
    pdf.gap(6)

    # --- Process ---
    pdf.h2("How it works: steps")
    steps_en = [
        "1. In the Utilities section, click 'Select CSV'.",
        "2. Choose the file from your computer or mobile device.",
        "3. Review the preview: the table shows all rows read from the file.",
        "   Rows with missing required fields are highlighted in red.",
        "4. If everything looks correct, click 'Import (N rows)'.",
        "5. The system displays the result: rows imported, skipped and errors.",
    ]
    for s in steps_en:
        pdf.body(s, indent=3)
        pdf.gap(1)
    pdf.gap(6)

    # --- Tickers ---
    pdf.h2("Identifying a security: Yahoo Finance ticker")
    pdf.body(
        "Each CSV row identifies the security using the 'ticker' field, which must "
        "match exactly the Yahoo Ticker registered in the application's securities "
        "catalogue. Examples: SAN.MC (Santander), BBVA.MC (BBVA), AAPL (Apple)."
    )
    pdf.gap(2)
    pdf.body(
        "IMPORTANT: If the ticker does not exist in the catalogue, the row is rejected "
        "with an error message, but the rest of the file is processed normally. "
        "An administrator must add the security to the catalogue before importing."
    )
    pdf.gap(6)

    # --- Column structure ---
    pdf.h2("CSV structure: columns")
    pdf.body("The first row must be the header with these exact names:")
    pdf.gap(3)
    pdf.table_row("Column", "Required", "Type / Values", "Description", header=True)
    cols_en = [
        ("type",            "Yes",         "buy / sell / dividend",     "Operation type"),
        ("ticker",          "Yes",         "text",                      "Yahoo Ticker (uppercase)"),
        ("date",            "Yes",         "YYYY-MM-DD",                "Operation date"),
        ("shares",          "Yes",         "number > 0",                "Shares traded (buy/sell) or shares at date (dividend)"),
        ("price",           "buy/sell",    "number > 0",                "Price per share (buy/sell only)"),
        ("gross_per_share", "dividend",    "number > 0",                "Gross dividend per share"),
        ("gross_amount",    "No",          "number > 0",                "Total gross amount (calculated if omitted)"),
        ("fee",             "No",          "number >= 0",               "Brokerage fee (default: 0)"),
        ("withholding_tax", "No",          "number >= 0",               "Withholding tax on dividend (default: 0)"),
        ("currency",        "No",          "EUR / USD",                 "Currency (default: EUR)"),
        ("exchange_rate",   "No",          "number > 0",                "EUR/USD ECB rate (required if USD, must != 1)"),
    ]
    for row in cols_en:
        pdf.table_row(*row)
    pdf.gap(6)

    # --- Rules by type ---
    pdf.h2("Rules by operation type")
    rules_en = [
        ("buy / sell",  "price is required. fee and exchange_rate are optional."),
        ("dividend",    "gross_per_share is required. gross_amount is optional: if omitted "
                        "it is calculated as shares x gross_per_share. withholding_tax "
                        "captures the tax withheld by the broker."),
        ("USD",         "If currency='USD', exchange_rate must be the ECB EUR/USD rate on "
                        "the operation date (never 1). "
                        "If currency='EUR', exchange_rate must be 1 or left empty."),
    ]
    for tipo, desc in rules_en:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 110, 60)
        pdf.cell(0, 6, tipo)
        pdf.ln(4)
        pdf.body(desc, indent=5)
        pdf.gap(3)
    pdf.gap(4)

    # --- Deduplication ---
    pdf.h2("Deduplication (idempotent import)")
    pdf.body("The system detects duplicate operations using these criteria:")
    pdf.gap(2)
    pdf.body("  Buy/sell:  same date + type + shares + price + fee.", indent=3)
    pdf.body("  Dividend:  same date + total gross amount.", indent=3)
    pdf.gap(2)
    pdf.body(
        "If a row already exists in the portfolio with the same values, it is silently "
        "skipped (counted as 'skipped', not as an error). This means you can reimport "
        "the same file multiple times without any risk."
    )
    pdf.gap(6)

    # --- Example ---
    pdf.h2("Example CSV file")
    pdf.set_font("Courier", "", 8)
    pdf.set_text_color(30, 30, 30)
    pdf.set_fill_color(240, 240, 240)
    for line in example.strip().split("\n"):
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 5, line, border=0, fill=True)
        pdf.ln()
    pdf.gap(3)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.body(
        "Note: in the AAPL dividend row, gross_amount is omitted; the system "
        "calculates it as 10 x 0.24 = 2.40. In the SAN.MC dividend it is given "
        "explicitly as 2.50 (the broker's actual figure, which may differ due to rounding)."
    )

    pdf.output(path)
    print(f"PDF generado: {path}")


if __name__ == "__main__":
    build_pdf(OUTPUT)
