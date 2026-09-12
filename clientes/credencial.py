"""
La credencial del socio, dibujada como imagen.

Antes era una pagina HTML que se mandaba a imprimir: para pasarla por WhatsApp
habia que guardarla como PDF, y un PDF en un chat casi nadie lo abre. Una
imagen se manda, se ve en la burbuja y se guarda en el carrete.

El dibujo esta aqui y no en una plantilla a proposito. Tener la tarjeta en CSS
para la pantalla y otra vez en Pillow para el archivo son dos disenos que se
separan a la primera correccion: la pagina ensena exactamente esta imagen.

Las medidas van en milimetros de tarjeta bancaria (ID-1, 85.6 x 54 mm) y se
escalan al dibujar. Asi se puede seguir hablando de "el retrato mide 22 mm" y,
de paso, lo que se imprima sale del tamano correcto.
"""

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageOps

#: Pixeles por milimetro. Con 14 la tarjeta sale de 1198 px de ancho: nitida en
#: un telefono y, si se imprime, a unos 355 ppp.
ESCALA = 14

ANCHO_MM, ALTO_MM = 85.6, 54
RADIO_MM = 3.5
MARGEN_MM = 3.5          # aire alrededor, para que se vean las esquinas
TIRA_MM = 8              # la franja de color de arriba
PADDING_MM = 4
RETRATO_MM = (22, 30)

FONDO = (236, 236, 239)  # el mismo gris de papel que tenia la pagina
BLANCO = (255, 255, 255)


def _px(mm):
    return round(mm * ESCALA)


def _fuente(mm):
    """
    La tipografia que trae Pillow (Aileron). Se usa la incluida y no la del
    panel para no cargar un binario de fuente al repositorio solo por esto.
    """
    return ImageFont.load_default(size=_px(mm))


def _rgb(hex_color, defecto=(0, 0, 0)):
    valor = (hex_color or '').lstrip('#')
    if len(valor) != 6:
        return defecto
    try:
        return tuple(int(valor[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return defecto


def _texto(lienzo, xy, texto, fuente, color, grueso=0, tracking=0, ancla='la'):
    """
    Escribe una linea.

    `grueso` finge la negrita engordando el trazo, porque la fuente incluida
    solo viene en redonda. `tracking` separa las letras, que es lo unico que
    hace legible un rotulo en mayusculas y chiquito.
    """
    x, y = xy
    if not tracking:
        lienzo.text((x, y), texto, font=fuente, fill=color, anchor=ancla,
                    stroke_width=grueso, stroke_fill=color)
        return

    # Letra por letra, que es la unica forma de separarlas: el ancla se aplica
    # a cada una, asi que solo valen las de alineacion horizontal izquierda.
    for letra in texto:
        lienzo.text((x, y), letra, font=fuente, fill=color, anchor=ancla,
                    stroke_width=grueso, stroke_fill=color)
        x += lienzo.textlength(letra, font=fuente) + tracking


def _acortar(lienzo, texto, fuente, ancho_max, tracking=0):
    """Recorta con puntos suspensivos lo que no cabe de ancho."""
    def mide(cadena):
        return (lienzo.textlength(cadena, font=fuente)
                + tracking * max(len(cadena) - 1, 0))

    if mide(texto) <= ancho_max:
        return texto
    while texto and mide(f'{texto}...') > ancho_max:
        texto = texto[:-1]
    return f'{texto}...'


def _partir(lienzo, texto, fuente, ancho_max, renglones=2):
    """
    Parte el nombre en renglones sin desbordar la tarjeta. Lo que no quepa se
    corta con puntos: mas vale un nombre recortado que uno pisando el borde.
    """
    pendientes = (texto or '').split()
    lineas = []
    actual = ''

    while pendientes and len(lineas) < renglones:
        prueba = f'{actual} {pendientes[0]}'.strip()
        if actual and lienzo.textlength(prueba, font=fuente) > ancho_max:
            lineas.append(actual)
            actual = ''
            continue
        actual = prueba
        pendientes.pop(0)

    if actual and len(lineas) < renglones:
        lineas.append(actual)

    # Sobraron palabras, o una sola palabra ya era mas larga que el hueco.
    if pendientes and lineas:
        lineas[-1] += ' ' + ' '.join(pendientes)
    return [_acortar(lienzo, linea, fuente, ancho_max) for linea in lineas] or ['']


def _recorte(archivo, ancho, alto, radio):
    """Una foto recortada al hueco y con las esquinas redondeadas."""
    try:
        with archivo.open('rb') as datos:
            imagen = Image.open(datos)
            imagen.load()
    except (OSError, ValueError):
        # No esta en el bucket, o no es una imagen. La credencial se entrega
        # igual con la inicial: es una tarjeta, no un tramite.
        return None

    imagen = ImageOps.exif_transpose(imagen).convert('RGB')
    imagen = ImageOps.fit(imagen, (ancho, alto), method=Image.LANCZOS)
    imagen.putalpha(_mascara(ancho, alto, radio))
    return imagen


def _mascara(ancho, alto, radio):
    mascara = Image.new('L', (ancho, alto), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        (0, 0, ancho - 1, alto - 1), radius=radio, fill=255
    )
    return mascara


def pie(cliente):
    """
    Los renglones de abajo de la tarjeta: hasta cuando le vale y en que sede.

    Esta fuera de `dibujar` porque es lo unico de la credencial que decide
    algo, y asi se puede comprobar sin ponerse a mirar pixeles.
    """
    vigente = cliente.membresia_vigente
    lineas = [
        f'Vigente hasta {vigente.fin.strftime("%d/%m/%Y")}' if vigente
        else 'Sin membresia vigente'
    ]
    if cliente.sucursal:
        lineas.append(cliente.sucursal.nombre)
    return lineas


def dibujar(cliente):
    """Devuelve la credencial del socio como imagen de Pillow."""
    gym = cliente.gym
    acento = _rgb(gym.color_primario, (245, 197, 24))
    oscuro = _rgb(gym.color_secundario, (17, 17, 17))
    sobre_acento = _rgb(gym.color_primario_texto, (11, 11, 15))

    ancho, alto = _px(ANCHO_MM), _px(ALTO_MM)
    pad, tira = _px(PADDING_MM), _px(TIRA_MM)

    # La tarjeta se dibuja cuadrada y se redondea al final con una mascara: asi
    # ningun elemento tiene que saber donde estan las esquinas.
    tarjeta = Image.new('RGB', (ancho, alto), oscuro)
    # El modo RGBA es lo que hace que los blancos con alfa se mezclen con el
    # fondo en vez de abrir un agujero transparente en la tarjeta.
    lienzo = ImageDraw.Draw(tarjeta, 'RGBA')

    # --- La franja de color, con el logo y el nombre del gimnasio ----------
    lienzo.rectangle((0, 0, ancho, tira), fill=acento)

    x = pad
    if gym.logo:
        lado = _px(5)
        logo = _recorte(gym.logo, lado, lado, _px(1))
        if logo:
            tarjeta.paste(logo, (x, (tira - lado) // 2), logo)
            x += lado + _px(2)

    fuente_gym, tracking_gym = _fuente(3.1), _px(0.08)
    _texto(lienzo, (x, tira / 2),
           _acortar(lienzo, gym.nombre.upper(), fuente_gym, ancho - x - pad,
                    tracking_gym),
           fuente_gym, sobre_acento, grueso=1, tracking=tracking_gym, ancla='lm')

    # --- El cuerpo: retrato y datos ---------------------------------------
    arriba = tira + pad
    ancho_retrato, alto_retrato = _px(RETRATO_MM[0]), _px(RETRATO_MM[1])
    radio_retrato = _px(2)

    retrato = (
        _recorte(cliente.foto, ancho_retrato, alto_retrato, radio_retrato)
        if cliente.foto else None
    )
    if retrato:
        tarjeta.paste(retrato, (pad, arriba), retrato)
    else:
        lienzo.rounded_rectangle(
            (pad, arriba, pad + ancho_retrato, arriba + alto_retrato),
            radius=radio_retrato, fill=(*BLANCO, 26),
            outline=(*BLANCO, 56), width=max(_px(0.3), 1),
        )
        lienzo.text(
            (pad + ancho_retrato / 2, arriba + alto_retrato / 2),
            (cliente.nombre or '?')[:1].upper(),
            font=_fuente(9), fill=(*BLANCO, 115), anchor='mm',
        )

    datos_x = pad + ancho_retrato + pad
    ancho_datos = ancho - datos_x - pad
    y = arriba

    _texto(lienzo, (datos_x, y), 'SOCIO', _fuente(2.2), (*BLANCO, 128),
           tracking=_px(0.35))
    y += _px(3.6)

    fuente_nombre = _fuente(4.4)
    for linea in _partir(lienzo, cliente.nombre, fuente_nombre, ancho_datos):
        _texto(lienzo, (datos_x, y), linea, fuente_nombre, BLANCO, grueso=1)
        y += _px(5.4)

    # El pie va pegado al borde de abajo y el numero se centra en el hueco que
    # quede entre los dos. Asi un nombre de dos renglones aprieta el espacio en
    # vez de dejar un agujero, y dos credenciales seguidas se parecen.
    lineas_pie = pie(cliente)
    fuente_pie = _fuente(2.6)
    alto_pie = _px(3.3) * len(lineas_pie)

    fuente_numero = _fuente(8.5)
    hueco_arriba, hueco_abajo = y, alto - pad - alto_pie
    # La caja real de los digitos, no el alto de la fuente: centrar por el alto
    # nominal deja el numero bailando segun cuanto aire traiga la tipografia.
    caja = lienzo.textbbox((0, 0), cliente.numero_usuario, font=fuente_numero)
    _texto(lienzo,
           (datos_x,
            hueco_arriba + (hueco_abajo - hueco_arriba - (caja[3] - caja[1])) / 2
            - caja[1]),
           cliente.numero_usuario, fuente_numero, acento, grueso=2,
           tracking=_px(0.3))

    y_pie = hueco_abajo
    for linea in lineas_pie:
        _texto(lienzo, (datos_x, y_pie),
               _acortar(lienzo, linea, fuente_pie, ancho_datos),
               fuente_pie, (*BLANCO, 158))
        y_pie += _px(3.3)

    # --- Sobre el papel ----------------------------------------------------
    margen = _px(MARGEN_MM)
    lamina = Image.new('RGB', (ancho + margen * 2, alto + margen * 2), FONDO)
    lamina.paste(tarjeta, (margen, margen), _mascara(ancho, alto, _px(RADIO_MM)))
    return lamina


def png(cliente):
    """La credencial lista para mandar, en bytes."""
    memoria = BytesIO()
    dibujar(cliente).save(memoria, format='PNG', optimize=True)
    return memoria.getvalue()
