"""
Genera instrucciones.pdf para FJS Finanzas v1.2.0.
Ejecutar desde la raiz del proyecto:
  python gen_instrucciones.py
"""
from fpdf import FPDF

VERSION = "1.2.0"
TITLE   = f"FJS Finanzas {VERSION} - Manual de usuario"

SECTIONS = [
    ("Descripcion general", [
        "FJS Finanzas es una aplicacion web personal de seguimiento de cartera de inversion. "
        "Permite registrar compras y ventas de acciones, seguir el valor de mercado en tiempo real, "
        "generar informes fiscales IRPF y gestionar el catalogo de mercados y valores.",
        "",
        "Caracteristicas principales:",
        "  - Multiusuario con control de acceso por contrasena.",
        "  - Responsive: funciona en escritorio y telefono movil.",
        "  - Instalable como PWA (Progressive Web App).",
        "  - Despliegue mediante contenedor Docker (servicio unico).",
        "  - Base de datos SQLite en volumen persistente.",
        "  - Datos de mercado via Yahoo Finance.",
        "  - Tipos de cambio EUR/USD del Banco Central Europeo.",
    ]),
    ("Instalacion (Docker)", [
        "1. Copiar docker-compose.yml y .env.example -> .env",
        "2. Editar .env y establecer SECRET_KEY con un valor aleatorio largo.",
        "3. Ejecutar: docker compose up -d",
        "4. Crear el primer usuario administrador desde la consola del contenedor:",
        "     docker exec -it finanzas python -m app.scripts.create_user USUARIO CLAVE --admin",
        "5. Abrir el navegador en http://localhost:8080",
        "",
        "El contenedor expone el puerto 8080. La base de datos se almacena en un volumen",
        "persistente (./data/finanzas.db).",
    ]),
    ("Novedades en v1.2.0", [
        "Panel de Administracion ampliado:",
        "  - Gestion de Mercados: el administrador puede crear, editar y eliminar mercados",
        "    (codigo, nombre, ticker del indice, divisa y ventana fiscal IRPF en dias).",
        "  - Gestion de Valores: las operaciones de alta, edicion y borrado de valores del",
        "    catalogo se han movido al Panel de Administracion y requieren rol admin.",
        "  - Configuracion del intervalo de refresco de precios: entre 5 y 60 minutos.",
        "  - El boton 'Actualizar precios (todos)' tambien se ha movido al Panel de Admin.",
        "",
        "Mejoras en Explorador de Mercados:",
        "  - Las pestanas (IBEX 35, Mercado Continuo, Nasdaq, etc.) se cargan dinamicamente",
        "    desde la base de datos; se pueden anadir nuevos mercados sin reiniciar.",
        "  - Marca de tiempo 'Precios actualizados' visible en cada pestana.",
        "",
        "Mejoras fiscales:",
        "  - Ventana de recompra IRPF configurable por mercado en dias",
        "    (por defecto 60 dias en mercados espanoles, 365 dias en Nasdaq).",
        "",
        "Refresco automatico de precios:",
        "  - El scheduler actualiza los snapshots cada N minutos durante el dia",
        "    (configurable desde el Panel de Administracion).",
    ]),
    ("Panel de Administracion (rol admin)", [
        "Accesible solo para usuarios con rol administrador. Al iniciar sesion, el admin",
        "accede directamente al Panel de Administracion en lugar de la aplicacion normal.",
        "",
        "Secciones del panel:",
        "",
        "1. Gestion de usuarios:",
        "   Crear, cambiar contrasena, cambiar rol y eliminar usuarios.",
        "",
        "2. Catalogo de valores:",
        "   Alta, edicion y borrado de valores. Para cada valor: nombre, ISIN,",
        "   Yahoo Ticker, Google Ticker, mercado y divisa.",
        "   No es posible borrar un valor con posiciones asociadas.",
        "",
        "3. Mercados:",
        "   Alta, edicion y borrado de mercados. Campos: codigo (clave unica),",
        "   nombre, ticker del indice de referencia, divisa y dias de ventana fiscal.",
        "",
        "4. Configuracion:",
        "   Intervalo de refresco de snapshots (5-60 minutos).",
        "   Boton 'Actualizar precios (todos)': fuerza el refresco inmediato.",
    ]),
    ("Explorador de Mercados", [
        "Pestanas dinamicas: una por cada mercado definido en la BD, mas 'Favoritos'.",
        "",
        "Cabecera del indice: nombre, precio actual, variacion % del dia y sparkline",
        "del ultimo anio del indice representativo del mercado.",
        "",
        "Tabla de valores - columnas:",
        "  Nombre, ISIN, Google Ticker, Precio, Var.% dia,",
        "  Min.1a, Min.2a, Min.5a, Max.1a, Dividendo,",
        "  Precio objetivo compra, % hasta objetivo, Alerta Comprar,",
        "  Favorito (estrella); en Favoritos: papelera en su lugar.",
        "",
        "Indicador MinBadge (naranja): aparece cuando el precio actual esta en o por",
        "debajo del minimo de 1, 2 o 5 anios; muestra siempre el intervalo mas amplio.",
        "",
        "Precio objetivo de compra: editable en linea en la pestana Favoritos.",
        "Si el precio cae por debajo del objetivo aparece '!Comprar!' en verde.",
        "",
        "Marca de tiempo: indica cuando se actualizaron los precios por ultima vez.",
    ]),
    ("Cartera", [
        "Resumen (7 tarjetas): Invertido, Valor actual, Diferencia (euros y %),",
        "  B/P latente, Dividendos, Var. hoy, Beneficio realizado.",
        "",
        "Tabla de posiciones abiertas (16 columnas):",
        "  Nombre, Acciones, Precio medio, Invertido, Precio actual,",
        "  Valor actual, % diff, Var. euros, Var. hoy %, Var. hoy euros,",
        "  Dividendos, B/P Total, Precio obj. venta, % hasta obj.,",
        "  Max. 1a, Alerta Vender.",
        "",
        "Tabla de posiciones cerradas: valores ya vendidos con resumen de coste,",
        "precio de venta, beneficio y dividendos cobrados.",
    ]),
    ("Detalle de valor", [
        "Accesible desde Cartera (clic en el nombre del valor) o desde el Explorador.",
        "",
        "Cabecera: ticker, nombre, mercado, divisa, ISIN, Google Ticker.",
        "Botones: Favorito, Editar, Actualizar (refresca el precio del valor).",
        "",
        "Tarjetas de resumen: precio actual, variacion %, min./max. 1 anio.",
        "Tarjetas de posicion: acciones, valor actual, invertido, B/P latente,",
        "  B/P venta, dividendos, comisiones, B/P total.",
        "",
        "Grafico de evolucion del ultimo anio.",
        "",
        "Tablas CRUD: Compras, Ventas, Dividendos.",
        "  Cada fila tiene botones de edicion y borrado.",
        "  Boton '+ Anadir' en cada tabla.",
        "",
        "Notas de posicion: campo de texto libre editable en linea.",
    ]),
    ("Utilidades", [
        "Cambiar contrasena: formulario para cambiar la contrasena del usuario actual.",
        "",
        "Copia de seguridad:",
        "  - Exportar JSON: descarga un fichero con todas las posiciones, transacciones",
        "    y dividendos de todos los usuarios.",
        "  - Importar JSON: carga un fichero exportado previamente.",
        "    La importacion es idempotente: no duplica registros ya existentes.",
        "",
        "Informe fiscal (IRPF):",
        "  - Seleccionar el anio de la campana de la renta.",
        "  - Descargar PDF: genera el informe con los calculos FIFO, aplicando",
        "    la regla antielusion de recompra en el plazo configurado por mercado.",
    ]),
    ("Scheduler - tareas automaticas", [
        "El scheduler ejecuta dos tipos de tareas:",
        "",
        "1. Actualizacion nocturna (06:30 hora local):",
        "   Descarga el historico de precios y calcula indicadores de rango",
        "   (min./max. 1, 2 y 5 anios) para todos los valores del catalogo.",
        "",
        "2. Refresco de snapshots (cada N minutos, configurable desde el panel admin):",
        "   Obtiene el precio de cierre mas reciente y la variacion diaria.",
        "   Intervalo minimo: 5 minutos. Intervalo maximo: 60 minutos.",
    ]),
]


class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(80, 80, 80)
        self.cell(0, 8, TITLE, align="R")
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"FJS Finanzas {VERSION}  -  Pag. {self.page_no()}", align="C")


def build_pdf(path: str) -> None:
    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 20, 20)
    pdf.add_page()

    # Title block
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(30, 30, 30)
    pdf.ln(20)
    pdf.cell(0, 12, "FJS Finanzas", align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 8, f"Manual de usuario - Version {VERSION}", align="C")
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, "Aplicacion web de seguimiento de cartera de inversion", align="C")
    pdf.ln(30)

    for section_title, lines in SECTIONS:
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(20, 80, 160)
        pdf.cell(0, 8, section_title)
        pdf.ln(2)
        pdf.set_draw_color(20, 80, 160)
        pdf.set_line_width(0.4)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(4)

        for line in lines:
            if line == "":
                pdf.ln(3)
                continue
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(40, 40, 40)
            indent = 4 if line.startswith("  ") else 0
            pdf.set_x(pdf.l_margin + indent)
            pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin - indent, 5, line.strip())
        pdf.ln(6)

    pdf.output(path)
    print(f"PDF generado: {path}")


if __name__ == "__main__":
    build_pdf("instrucciones.pdf")
