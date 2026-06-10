"""
Genera instrucciones.pdf para JSG Soft..
Ejecutar desde la raiz del proyecto:
  python gen_instrucciones.py
"""
from fpdf import FPDF

VERSION = "1.13.1"
TITLE   = f"JSG Soft. {VERSION} - Manual de usuario"

SECTIONS = [
    ("Descripcion general", [
        "JSG Soft. es una aplicacion web personal de seguimiento de cartera de inversion. "
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
        "1. Copiar docker-compose.yml, Caddyfile y .env.example -> .env",
        "2. Editar .env: establecer SECRET_KEY (valor aleatorio largo),",
        "   DOMAIN (tu dominio real) y COOKIE_SECURE=true.",
        "3. Ejecutar: docker compose up -d",
        "   Caddy obtiene el certificado SSL automaticamente en el primer arranque.",
        "4. Crear el primer usuario administrador desde la consola del contenedor:",
        "     docker exec -it finanzas-finanzas-1 python -m app.scripts.create_user USUARIO CLAVE --admin",
        "5. Abrir el navegador en https://tu-dominio.com",
        "",
        "El acceso externo pasa por Caddy (puertos 80 y 443).",
        "La base de datos se almacena en un volumen Docker persistente (finanzas-data).",
        "",
        "Para ver el proceso detallado, ver la seccion",
        "'Despliegue en VPS con HTTPS (Caddy)' mas adelante.",
    ]),
    ("Despliegue en VPS con HTTPS (Caddy)", [
        "Caddy actua como proxy inverso y gestiona el certificado SSL de Let's Encrypt",
        "de forma completamente automatica: lo obtiene en el primer arranque y lo",
        "renueva antes de que caduque, sin ninguna intervencion manual.",
        "",
        "Requisitos previos:",
        "  - Servidor VPS con Ubuntu/Debian y acceso root por SSH.",
        "  - Dominio registrado con un registro A apuntando a la IP publica del VPS.",
        "  - Docker y Docker Compose instalados en el VPS.",
        "  - Puertos 80 y 443 abiertos en el firewall del VPS y del proveedor.",
        "",
        "PASO 1 - Verificar que el dominio resuelve al VPS:",
        "  nslookup tudominio.com",
        "  La IP devuelta debe coincidir con la IP publica del servidor.",
        "  Si no es asi, espera a que propaguen los DNS (hasta 24 h).",
        "",
        "PASO 2 - Abrir puertos en el firewall del VPS (UFW):",
        "  sudo ufw allow OpenSSH",
        "  sudo ufw allow 80/tcp",
        "  sudo ufw allow 443/tcp",
        "  sudo ufw enable",
        "  sudo ufw status",
        "  Importante: verificar tambien en el panel web del proveedor (Piensa,",
        "  Hetzner, etc.) que los puertos 80 y 443 no esten bloqueados por el",
        "  firewall de la plataforma.",
        "",
        "PASO 3 - Detener el contenedor actual (si hay uno corriendo en el puerto 80):",
        "  docker compose down",
        "",
        "PASO 4 - Subir los ficheros actualizados al VPS:",
        "  Copiar al servidor: docker-compose.yml, Caddyfile, .env.example.",
        "  Si ya tienes un .env, editarlo directamente (no sobreescribir).",
        "",
        "PASO 5 - Editar el fichero .env en el servidor:",
        "  nano .env",
        "  Establecer o verificar estos valores:",
        "    SECRET_KEY=<clave aleatoria larga>",
        "    DOMAIN=tudominio.com",
        "    COOKIE_SECURE=true",
        "  Guardar y cerrar (Ctrl+O, Ctrl+X en nano).",
        "",
        "PASO 6 - Arrancar los contenedores:",
        "  docker compose up -d",
        "  Caddy detecta el dominio real, contacta con Let's Encrypt y obtiene",
        "  el certificado automaticamente. El proceso tarda unos 10-30 segundos.",
        "  Ver los logs de Caddy para confirmar:",
        "    docker compose logs caddy",
        "  Buscar la linea: certificate obtained successfully",
        "",
        "PASO 7 - Verificacion final:",
        "  - Abrir https://tudominio.com en el navegador.",
        "  - Comprobar que aparece el candado de seguridad en la barra de direccion.",
        "  - Comprobar que http://tudominio.com redirige automaticamente a HTTPS.",
        "  - Hacer login y verificar que la sesion funciona correctamente.",
        "",
        "Renovacion automatica del certificado:",
        "  Caddy renueva el certificado automaticamente antes de que caduque",
        "  (Let's Encrypt emite certificados de 90 dias; Caddy los renueva a los 60).",
        "  No hay que configurar ningun cron job ni ejecutar ningun comando.",
        "",
        "Notas:",
        "  - El Caddyfile incluido tiene una sola linea de configuracion:",
        "      {$DOMAIN} { reverse_proxy finanzas:8000 }",
        "    Caddy lee la variable DOMAIN del entorno (definida en .env).",
        "  - Para pruebas locales con Docker sin dominio real, usar DOMAIN=localhost",
        "    y COOKIE_SECURE=false; Caddy servira HTTP sin intentar obtener cert.",
        "  - Los certificados y la config de Caddy se guardan en el volumen",
        "    caddy-data (persistente); no se pierden al reiniciar el contenedor.",
    ]),
    ("Novedades en v1.5.0", [
        "ETFs y criptomonedas:",
        "  - Soporte completo para ETFs (fondos cotizados) y criptomonedas como",
        "    nuevos tipos de activos, utilizando el mecanismo de mercados dinamicos.",
        "  - Se incluyen dos catalogos listos para importar desde el Panel de Admin:",
        "    * catalogo-etfs-completo.json: 47 ETFs (29 en EUR, 18 en USD)",
        "      en los mercados 'ETFs EUR' y 'ETFs USD'.",
        "    * catalogo-crypto.json: 31 criptomonedas en el mercado 'Crypto' (USD).",
        "  - Ventana fiscal de 1 dia para crypto: en Espana las criptos no tienen",
        "    regla de recompra (no se aplica la norma de 2 meses).",
        "",
        "Orden configurable de pestanas de mercados:",
        "  - El administrador puede reordenar las pestanas del Explorador de Mercados",
        "    usando los botones de subir / bajar en el Panel de Administracion.",
        "  - El orden se guarda en la base de datos y se aplica a todos los usuarios.",
        "",
        "Selector de idioma Espanol / Ingles:",
        "  - En la seccion Utilidades hay un selector de idioma.",
        "  - La preferencia se guarda en el navegador (localStorage).",
        "  - Los textos de la interfaz cambian inmediatamente al seleccionar.",
        "",
        "Mejoras visuales:",
        "  - Badge de tipo de activo (ETF / Crypto / Accion) en tabla y tarjetas.",
        "  - Columnas ISIN, Google Ticker y Dividendo ocultas automaticamente",
        "    si ningun valor del mercado activo tiene ese dato (ej. Crypto).",
        "  - Precios adaptativos: 2, 4 o 6 decimales segun la magnitud del precio",
        "    (necesario para micro-caps como SHIB cuyo precio es menor que 0,00001).",
        "  - Las pestanas de mercado hacen scroll horizontal en lugar de envolver,",
        "    evitando que la tabla quede desplazada hacia abajo en movil.",
    ]),
    ("Novedades en v1.4.3", [
        "Importacion y exportacion del catalogo de valores (administrador):",
        "",
        "  Nueva seccion 'Catalogo de valores' en el Panel de Administracion:",
        "",
        "  - Exportar catalogo: descarga un fichero JSON con todos los mercados",
        "    y valores actualmente registrados en el sistema. Util para migrar",
        "    el catalogo a un servidor nuevo sin tener que introducirlos a mano.",
        "",
        "  - Importar catalogo: sube un JSON (propio o el fichero de referencia",
        "    catalogo-valores.json incluido en el paquete de instalacion) y aÃ±ade",
        "    los mercados y valores que no existan todavia.",
        "",
        "  Reglas de importacion:",
        "    * Mercados: indice = codigo de mercado. Si ya existe, se omite.",
        "    * Valores: indice = Yahoo Ticker (unico global). Si el ticker ya",
        "      existe en cualquier mercado, no se importa ni se cambia de mercado.",
        "    * Si el mercado de un valor no existe (ni en la BD ni en el mismo",
        "      lote de importacion), el valor se omite y se informa al admin.",
        "    * Los mercados del mismo lote se importan antes que los valores,",
        "      permitiendo hacer una importacion inicial completa en una sola vez.",
        "    * Al terminar se muestra un resumen con los contadores de importados",
        "      y omitidos para mercados y para valores.",
        "",
        "  Fichero catalogo-valores.json:",
        "    Incluido en el paquete de instalacion. Contiene 3 mercados",
        "    (IBEX 35, Mercado Continuo, Nasdaq) y 93 valores con sus Yahoo",
        "    tickers, Google tickers, ISINs (donde se conocen) y monedas.",
        "    La composicion del IBEX35 es aproximada a 2025; verificar en BME.",
    ]),
    ("Novedades en v1.4.2", [
        "Mejoras de usabilidad y presentacion:",
        "",
        "  1. Informe fiscal PDF - resumen ejecutivo en pagina 1:",
        "     El informe imprimible ahora incluye una primera pagina de resumen",
        "     con cuatro indicadores clave: resultado neto de ventas, dividendos",
        "     netos (bruto y retencion), comisiones pagadas y base imponible",
        "     estimada (con tramo marginal y cuota estimada).",
        "     Debajo aparece una barra de color que muestra como se distribuye",
        "     la base entre los tramos del ahorro IRPF (19%, 21%, 23%, 27%, 28%).",
        "     El detalle de operaciones se imprime a partir de la pagina 2.",
        "",
        "  2. Cabecera de la aplicacion en movil:",
        "     En dispositivos moviles la barra lateral de escritorio no es visible.",
        "     Ahora aparece una cabecera fija en la parte superior con el nombre",
        "     de la aplicacion y el numero de version, igual que en escritorio.",
    ]),
    ("Novedades en v1.4.1 - Correcciones", [
        "Seis bugs corregidos con tests de regresion (174 tests en total):",
        "",
        "  1. Porcentaje de retorno de cartera incorrecto:",
        "     El resumen de cartera mostraba un % de rentabilidad erroneo cuando",
        "     habia ganancias realizadas o dividendos cobrados. Solo contaba la",
        "     ganancia latente. Ahora refleja el beneficio total / capital invertido.",
        "",
        "  2. Importacion de backup USD con tipo de cambio 1 rompia la cartera:",
        "     Un backup con transacciones en USD y exchange_rate=1 se importaba",
        "     sin error, pero al cargar la cartera devolvÃ­a error 500. Ahora el",
        "     import rechaza esa combinacion incoherente con mensaje claro.",
        "",
        "  3. Importacion de backup permitia precio cero:",
        "     El endpoint de import aceptaba price=0 en transacciones, mientras",
        "     que la API normal lo rechaza. Ahora son coherentes.",
        "",
        "  4. Deduplicacion incorrecta en importacion de backup:",
        "     Dos transacciones del mismo dia con identicas acciones y precio",
        "     pero distinta comision se trataban como duplicadas; la segunda",
        "     se omitia silenciosamente. La clave de dedup incluye ahora la",
        "     comision y usa comparacion numerica (no textual) de Decimal.",
        "",
        "  5. Acciones vendidas incorrectas en posiciones cerradas con splits:",
        "     La columna 'Acciones vendidas' mezclaba unidades pre- y post-split",
        "     cuando habia ventas antes y despues de un split. Ahora el dato es",
        "     coherente con el calculo FIFO (equivalente post-split).",
        "",
        "  6. Deteccion de regla de recompra fiscal (informe IRPF):",
        "     Si habia dos compras el mismo dia y una era la emparejada por FIFO",
        "     con una venta con perdida, la otra compra del mismo dia no activaba",
        "     la regla de recompra aunque estuviera dentro del plazo. Corregido.",
    ]),
    ("Novedades en v1.4.0", [
        "Splits y contrasplits de valores (gestion admin):",
        "  - El administrador registra los eventos de split desde el Panel de",
        "    Administracion (seccion Catalogo de valores > boton 'Splits').",
        "  - Un split es global: se registra una vez y afecta automaticamente",
        "    a todos los usuarios que posean ese valor.",
        "  - El motor FIFO normaliza todas las transacciones anteriores a la",
        "    fecha efectiva del split antes de calcular posiciones y ganancias.",
        "    Invariante: el coste total de cada lote no cambia.",
        "  - Splits consecutivos se aplican en orden cronologico.",
        "  - El informe fiscal IRPF y el grafico de evolucion de cartera",
        "    tambien utilizan los datos normalizados.",
        "",
        "Pantalla de gestion de splits (AdminPanel > Splits):",
        "  - Fecha efectiva (ex-date), ratio Nuevas:Antiguas y nota opcional.",
        "  - Ejemplos: split 2:1 -> Nuevas=2, Antiguas=1;",
        "              contrasplit 1:2 -> Nuevas=1, Antiguas=2.",
        "  - Los splits se pueden borrar; los cambios son inmediatos.",
    ]),
    ("Novedades en v1.3.0", [
        "Control de suscripciones de usuarios (rol administrador):",
        "  - Habilitar o deshabilitar un usuario sin eliminar sus datos.",
        "    Al deshabilitar se puede aÃ±adir una anotacion (motivo).",
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
        "  - El valor por defecto es 'JSG Soft.'.",
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
        "   - Boton 'Splits': gestiona los eventos de split/contrasplit del valor.",
        "",
        "3. Mercados:",
        "   Alta, edicion y borrado de mercados. Campos: codigo (clave unica),",
        "   nombre, ticker del indice de referencia, divisa y dias de ventana fiscal.",
        "",
        "4. Configuracion:",
        "   - Nombre de la aplicacion: personalizable (por defecto 'JSG Soft.').",
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
        self.cell(0, 10, f"JSG Soft. {VERSION}  -  Pag. {self.page_no()}", align="C")


def build_pdf(path: str) -> None:
    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 20, 20)
    pdf.add_page()

    # Title block
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(30, 30, 30)
    pdf.ln(20)
    pdf.cell(0, 12, "JSG Soft.", align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 8, f"Manual de usuario  -  Version {VERSION}", align="C")
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
