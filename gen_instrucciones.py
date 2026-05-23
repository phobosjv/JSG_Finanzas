"""
Genera instrucciones.pdf para FJS Finanzas v1.2.0.
Ejecutar desde la raiz del proyecto:
  python gen_instrucciones.py
"""
from fpdf import FPDF

VERSION = "1.3.0"
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
    ("Novedades en v1.3.0", [
        "Control de suscripciones de usuarios (rol administrador):",
        "  - Habilitar o deshabilitar un usuario sin eliminar sus datos.",
        "    Al deshabilitar se puede añadir una anotacion (motivo).",
        "  - Si un usuario deshabilitado intenta hacer login, recibe el mensaje",
        "    'Contactar con el administrador'.",
        "  - Fecha de caducidad opcional por usuario: llegada la fecha, el usuario",
        "    se deshabilita automaticamente en el siguiente intento de login.",
        "  - Al volver a habilitar un usuario, se puede opcionalmente asignar",
        "    una nueva fecha de caducidad.",
        "  - Historial de estados por usuario: registro cronologico de altas,",
        "    habilitaciones, deshabilitaciones y caducidades, con fecha, hora",
        "    y nombre del administrador que realizo la accion.",
        "",
        "Nombre personalizable de la aplicacion:",
        "  - El administrador puede cambiar el nombre de la aplicacion desde",
        "    el Panel de Administracion (seccion Configuracion del sistema).",
        "  - El nombre nuevo aparece en la barra de titulo del navegador,",
        "    en la cabecera del menu lateral y en la pagina de login.",
        "  - El valor por defecto es 'FJS Finanzas'.",
        "",
        "Tema claro / oscuro (usuarios normales):",
        "  - Boton de alternancia en el pie del menu lateral.",
        "  - La preferencia se guarda en el navegador (localStorage).",
        "  - El tema oscuro es el valor por defecto.",
    ]),
    ("Novedades en v1.2.2", [
        "Correcciones de bugs:",
        "  - Marca de tiempo de actualizacion de precios ahora se muestra en la zona",
        "    horaria local del usuario (antes se mostraba siempre en UTC).",
        "  - Corregida validacion incompleta en edicion de transacciones: editar una",
        "    compra a menos acciones de las que cubren una venta ya registrada ahora",
        "    devuelve error 422 en lugar de corromper silenciosamente el FIFO.",
        "  - Borrar una compra que tiene ventas asociadas ahora devuelve 422.",
        "  - Correcto conteo de securities al intentar borrar un mercado con valores.",
        "  - PATCH de mercado ahora valida la divisa (solo EUR/USD) y que",
        "    fiscal_window_days sea >= 1.",
        "",
        "Nuevos tests de validacion (129 tests en total):",
        "  - Borrar compra con ventas cubiertas -> 422.",
        "  - Editar compra a menos acciones de las que cubren una venta -> 422.",
        "  - PATCH mercado con divisa invalida -> 422.",
        "  - PATCH mercado con ventana fiscal <= 0 -> 422.",
    ]),
    ("Novedades en v1.2.1", [
        "  - La marca de tiempo 'Precios actualizados' visible en el Explorador de",
        "    Mercados se adapta automaticamente a la zona horaria del usuario.",
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
        "   - Columna 'Estado': Activo (verde) o Inactivo (rojo).",
        "   - Columna 'Caduca': fecha de caducidad o '-' si no tiene.",
        "   - Boton 'Habilitar/Deshabilitar': cambia el estado con anotacion opcional.",
        "     Al habilitar se puede poner opcionalmente una fecha de caducidad.",
        "   - Boton 'Caducidad': establece o borra la fecha de caducidad.",
        "   - Boton 'Historial': muestra la linea de tiempo de cambios de estado.",
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
        "   - Nombre de la aplicacion: personalizable (por defecto 'FJS Finanzas').",
        "   - Intervalo de refresco de snapshots (5-60 minutos).",
        "   - Boton 'Actualizar precios (todos)': fuerza el refresco inmediato.",
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
