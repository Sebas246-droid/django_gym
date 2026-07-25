# GymPilot - Backend y front end

Implementacion de [README.md](README.md): backend completo y front end en dos
capas: la pagina publica de cada gimnasio y el panel de administracion.

## Puesta en marcha

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # opcional; por defecto usa SQLite

python manage.py migrate
python manage.py init_saas --demo   # roles, planes y gimnasio de prueba
python manage.py createsuperuser    # super administrador del SaaS
python manage.py runserver
```

Con `--demo` quedan creados:

| Usuario          | Contrasena | Rol            |
|------------------|------------|----------------|
| `admin_demo`     | demo12345  | Administrador  |
| `recepcion_demo` | demo12345  | Recepcion-Caja |

Para PostgreSQL: `docker compose up -d` y descomenta las variables
`POSTGRES_*` en `.env`.

El demo deja clientes en distintos estados para probar el acceso, ademas de
un catalogo de productos con existencias y una semana de asistencias para que
el tablero no se vea vacio:

| Numero | Cliente       | Al ingresar                    |
|--------|---------------|--------------------------------|
| `1000` | Ana Torres    | Verde, membresia vigente       |
| `1001` | Luis Ramirez  | Ambar, le quedan pocos dias    |
| `1002` | Sofia Mendez  | Rojo, membresia vencida        |
| `1003` | Carlos Vega   | Rojo, nunca compro membresia   |

## Front end

**Pagina publica** (`/g/<slug>/`, sin sesion). Es la portada del gimnasio:
frase principal, descripcion, galeria de fotos propias, boton de WhatsApp,
sucursales con mapa y acceso al sistema. Cada gimnasio elige sus colores en
`Sitio web`: se inyectan como variables CSS, asi que un solo archivo
[sitio.css](static/css/sitio.css) sirve a todos los gimnasios sin duplicar
hojas de estilo. La frase y la descripcion tienen texto generico por defecto,
de modo que la pagina se ve completa desde el primer dia.

El mapa usa el embed de OpenStreetMap a partir de la latitud y longitud de la
sucursal: no requiere API key ni cuenta de Google.

La raiz `/` manda al tablero si hay sesion; si no la hay y existe un solo
gimnasio publicado, muestra su pagina; en cualquier otro caso, al login.

**Tablero.** Es la primera pantalla del dia y la que se ensena al presentar el
sistema, asi que responde de un vistazo tres preguntas: cuanto entro hoy, cuanta
gente hay dentro ahora mismo, y a quien conviene llamar.

- Panel oscuro con el acento del gimnasio: ingresos del dia, desglose
  membresias/productos y barras de los ultimos 7 dias.
- "En el gimnasio ahora": sigue dentro quien su ultimo movimiento de hoy fue
  una entrada.
- "Salud de la cartera": barra apilada con al corriente, por vencer y sin
  membresia, mas el porcentaje de cobertura.
- Grafica de area de entradas de la semana, dibujada en SVG con las
  coordenadas calculadas en la vista (`DashboardView._serie`).
- Listas para actuar: por vencer, quienes no vienen hace 14 dias, lo mas
  vendido del mes, accesos de hoy y stock bajo minimo.

Ojo con la localizacion: el proyecto corre en espanol, donde el decimal se
escribe con coma. En SVG y en CSS eso rompe (`x="44,0"` se lee como dos
coordenadas y `width:50,0%` es invalido), asi que esos numeros van dentro de
`{% localize off %}` o con `|unlocalize`.

**Punto de venta** ([ventas/pos.py](ventas/pos.py)). Rejilla de productos como
tarjetas con su precio y existencia en la sucursal; un toque agrega una pieza.
El carrito vive a la derecha con mas, menos y quitar por linea, cliente
opcional, metodo de pago y descuento.

El carrito **no vive en la sesion: es una Venta en estado borrador**. Asi el
total, la validacion de stock y el descuento de inventario son exactamente los
mismos que en el resto del sistema, cada cajero tiene el suyo, y si se cierra
el navegador el carrito sigue ahi. Abrir la caja no crea nada: la venta nace
al agregar el primer producto.

Los productos agotados aparecen atenuados y no se pueden tocar; si aun asi
faltara stock al cobrar, la venta no se confirma y se avisa cuales productos
son. Un descuento mayor al total deja el total en cero, nunca en negativo.

**Panel de administracion.** Navegacion lateral fija con los modulos agrupados,
cabecera de pagina con migas y acciones, tarjetas de 16px de radio, sombras
suaves, neutros frios y tipografia Inter. Vive en
[gympilot.css](static/css/gympilot.css) y toma el acento del gimnasio. El menu
activo se deduce de la url en el context processor, no hay que declararlo vista
por vista.

El color de texto sobre el acento se calcula por luminancia
(`Gym.color_primario_texto`), asi que los botones siguen siendo legibles lo
mismo con un amarillo claro que con un azul oscuro.

**Kiosco de acceso** ([kiosco.html](templates/clientes/kiosco.html)). Pantalla
completa pensada para una tablet fija en la entrada, con la portada del sitio
de fondo. No tiene menu, ni metricas, ni listados: solo las casillas del numero,
el teclado y el boton de registrar entrada. Al completar el numero se envia
solo. En la esquina superior izquierda van la hora, la fecha y el unico atajo,
"No recuerdo mi numero", que abre la busqueda por nombre o telefono. Las
metricas del dia viven en el tablero, donde si tienen sentido.

El veredicto ocupa toda la tarjeta:

- verde si la membresia esta vigente
- ambar si quedan 3 dias o menos
- rojo si vencio, con la fecha, o si nunca compro

**Segundo paso.** A quien pasa (verde o ambar) se le pregunta ahi mismo que va
a entrenar, con el catalogo del gimnasio en botones grandes. Es opcional: la
entrada ya quedo registrada, elegir solo completa el dato en esa misma
asistencia, sin crear otra. A quien tiene la membresia vencida no se le ofrece.

La pantalla vuelve sola al teclado a los 7 segundos, o a los 16 si hay segundo
paso, para dar tiempo a elegir.

Cuatro decisiones que conviene tener presentes:

- El dialogo se dimensiona con `clamp()` sobre unidades `vh` en lugar de
  medidas fijas: ocupa lo maximo posible en cada tablet, en horizontal o
  vertical, sin desbordarse nunca.
- Las casillas se dibujan segun la numeracion real del gimnasio: cuatro digitos
  mientras los numeros vayan del 1000 al 9999.

- La asistencia **se registra tambien cuando la membresia esta vencida**. El
  sistema avisa en rojo, pero deja el rastro de que la persona se presento;
  quien decide si pasa es recepcion.
- El resultado viaja por sesion con patron POST-Redirect-GET, para que recargar
  la pantalla no duplique el registro. Hay una prueba que lo cubre.

**Numero de usuario.** `Cliente.numero_usuario` se asigna solo, consecutivo
desde el 1000 y por gimnasio: dos gimnasios distintos pueden tener el numero
1000 sin chocar, porque la unicidad es `(gym, numero_usuario)`.

## Estructura

```
config/          settings, urls
core/            Plan, Gym, GymImagen, Sucursal, GymModel (base), mixins, roles
accounts/        User (AbstractUser) + gestion de usuarios
clientes/        Cliente, Membresia, ClienteMembresia, Asistencia
entrenamiento/   Entrenamiento (catalogo)
inventario/      CategoriaProducto, Producto, InventarioSucursal, Proveedor, Compra
ventas/          Venta, VentaDetalle
templates/       plantillas por app, landing publica y kiosco
static/css/      gympilot.css (panel), sitio.css (pagina publica), kiosco.css
```

## Decisiones de la implementacion

**Aislamiento multi-tenant.** `GymModel` (en [core/models.py](core/models.py))
aporta `gym`, `activo`, `created_at` y `updated_at` a toda entidad de negocio.
El filtrado no depende de que cada vista lo recuerde: `GymQuerysetMixin`
([core/mixins.py](core/mixins.py)) recorta el queryset al gym del usuario y
`GymModelForm` ([core/forms.py](core/forms.py)) recorta cada combo relacionado.
Pedir un registro de otro gimnasio devuelve 404.

**Soft delete.** Ninguna vista borra. `SoftDeleteView` marca `activo = False`
y los listados solo muestran activos.

**Sucursal Principal automatica.** Signal `post_save` sobre `Gym`
([core/signals.py](core/signals.py)).

**Roles.** Groups nativos, creados por `init_saas` con sus permisos:
Administrador, Recepcion - Caja, Entrenador. Sin tablas propias de permisos.

**Limites del plan.** `Gym.puede_crear_sucursal()`, `puede_crear_usuario()` y
`puede_crear_cliente()` se validan al guardar.

**Cobros sin tabla Pago.** `ClienteMembresia` guarda precio, descuento,
metodo, fecha y el usuario que cobro. `fin` se calcula desde
`inicio + duracion_dias` de la membresia.

**Compras y ventas en dos pasos.** Se crea la cabecera en estado `borrador`,
se agregan los detalles y al confirmar se mueve el inventario:
compra suma, venta resta. Se agrego el campo `estado` (no esta en el README)
para que confirmar sea idempotente y el stock nunca se aplique dos veces.
La venta se rechaza si algun producto no tiene stock suficiente en la sucursal.

## Flujos cubiertos

1. Alta de gimnasio -> plan -> sucursal Principal -> usuario administrador
2. Alta de usuarios con sucursal y rol
3. Registro de clientes
4. Venta de membresia con registro del cobro
5. Check-in: buscar cliente, entrenamiento opcional, entrada/salida
6. Compras -> detalle -> confirmar -> stock +
7. Ventas -> detalle -> confirmar -> stock -

## Pruebas

```bash
python manage.py test
```

58 pruebas:

- [core/tests.py](core/tests.py) recorre el flujo del README completo, la no
  mezcla de datos entre gimnasios, el soft delete, los limites del plan y los
  calculos del tablero (quien sigue dentro, salud de la cartera, grafica).
- [ventas/tests.py](ventas/tests.py) cubre el punto de venta: carrito por
  cajero, sumar y quitar piezas, cobro con descuento y cliente, y los casos que
  no deben pasar (sin stock, carrito vacio, descuento invalido o excesivo).
- [accounts/tests.py](accounts/tests.py) cubre el staff: que el alta deje a la
  persona pudiendo entrar, el restablecimiento de contrasena, y que un
  administrador no alcance al staff de otro gimnasio.
- [clientes/tests.py](clientes/tests.py) cubre el acceso por numero en sus
  cuatro estados, el aislamiento del numero entre gimnasios, la no duplicacion
  al recargar, que el kiosco no exponga metricas ni listados, el segundo paso
  del entrenamiento (a quien se ofrece, que no duplique la asistencia y que no
  alcance a otro gimnasio) y la pagina publica.

## Pendiente para la siguiente etapa

- HTMX para el acceso sin recargar y busqueda incremental de clientes
- Reporte de corte de caja
- Fase 2: FastAPI, IA, Telegram, reconocimiento facial, API movil
