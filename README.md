 GymPilot
 
 
 
 Arquitectura
                    Internet
                        │
                        ▼
                Rayliway (Producción)
                        │
                        ▼
                    Django 
        ┌────────────────────────────────┐
        │ Authentication                 │
        │ Authorization (Groups)         │
        │ Django Admin                   │
        │ Templates + HTMX               │
        │ ORM                            │
        │ Business Logic                 │
        └────────────────────────────────┘
                        │
                        ▼
               PostgreSQL (Docker)

──────────────────────────────────────────────

Fase 2

FastAPI

• IA
• Telegram
• Reconocimiento facial
• API Mobile
Modelo SaaS

Se utilizará el modelo

Shared Database
Una sola base de datos

↓

Todos los gimnasios comparten la BD

↓

Cada tabla de negocio contiene gym_id

↓

Nunca se mezclan los datos.
Estructura del proyecto
config/

core/

accounts/

clientes/

inventario/

ventas/

entrenamiento/
CORE
Plan

Representa las características disponibles para cada cliente.

Plan

id

nombre

precio

usuarios_max

clientes_max

sucursales_max

activo
Gym

Representa al cliente del SaaS.

Gym

id

plan_id

nombre

slug

telefono

email

logo

fecha_alta

zona_horaria

moneda

activo

Relaciones

Plan

↓

Gym

↓

Todo el sistema
Sucursal

Cada gimnasio puede tener una o varias sucursales dependiendo de su plan.

Sucursal

id

gym_id

nombre

direccion

telefono

correo

responsable

activo

created_at

updated_at

Cuando un gimnasio se crea automáticamente también se crea una sucursal llamada Principal.

ACCOUNTS

Se utilizará el sistema de autenticación nativo de Django mediante AbstractUser.

User
User

id

gym_id

sucursal_id

username

email

password

first_name

last_name

telefono

foto

is_active

is_staff

is_superuser

Roles utilizando Groups

Administrador

Recepción - Caja

Entrenador

No se crearán tablas personalizadas para roles o permisos.

CLIENTES
Cliente
Cliente

id

gym_id

sucursal_id

nombre

telefono

correo

sexo

fecha_nacimiento

foto

nombre_contacto_emergencia

telefono_contacto_emergencia

activo
Membresia

Catálogo de membresías del gimnasio.

Membresia

id

gym_id

nombre

precio

duracion_dias

descripcion

activo
ClienteMembresia

Historial completo de compras de membresías.

ClienteMembresia

id

gym_id

cliente_id

membresia_id

inicio

fin

estado

precio

descuento

metodo_pago

fecha_pago

observaciones

usuario_id

Aquí queda registrado

quién realizó el cobro
cuánto pagó
cómo pagó
cuándo pagó

No será necesaria una tabla Pago.

Asistencia

Registro de entradas y salidas.

Asistencia

id

gym_id

sucursal_id

cliente_id

usuario_id

entrenamiento_id

fecha_hora

tipo
Entrada

Salida
ENTRENAMIENTO

No será un sistema completo de rutinas.

Será únicamente un catálogo configurable por cada gimnasio.

Entrenamiento

id

gym_id

nombre

descripcion

documento

video

activo

created_at

En futuras versiones la IA utilizará este registro para enviar automáticamente:

PDF
Videos
Rutinas
Mensajes por Telegram
INVENTARIO
CategoriaProducto
CategoriaProducto

id

gym_id

nombre

descripcion

activo
Producto

Catálogo de productos.

Producto

id

gym_id

categoria_id

codigo

nombre

marca

precio_compra

precio_venta

activo

No guarda stock.

InventarioSucursal

Stock por sucursal.

InventarioSucursal

id

producto_id

sucursal_id

stock

stock_minimo

Esto permitirá múltiples sucursales sin duplicar productos.

Proveedor
Proveedor

id

gym_id

nombre

telefono

correo

activo
Compra

Cabecera de compras.

Compra

id

gym_id

sucursal_id

proveedor_id

usuario_id

fecha

total
CompraDetalle
CompraDetalle

id

compra_id

producto_id

cantidad

precio

Al confirmar una compra

InventarioSucursal

+

cantidad
VENTAS
Venta
Venta

id

gym_id

sucursal_id

cliente_id (NULL)

usuario_id

fecha

subtotal

descuento

total

metodo_pago
VentaDetalle
VentaDetalle

id

venta_id

producto_id

cantidad

precio

Al confirmar una venta

InventarioSucursal

-

cantidad
Soft Delete

Ningún registro será eliminado físicamente.

Todas las tablas de negocio incluirán

activo

True

False

Esto permitirá conservar historial y evitar pérdidas de información.

Flujo completo del sistema
1. Alta de un gimnasio
Super Administrador

↓

Crear Gym

↓

Seleccionar Plan

↓

Crear Sucursal Principal

↓

Crear Usuario Administrador

↓

Asignar Group

↓

Enviar credenciales

↓

Gym listo para operar
2. Alta de usuarios
Administrador

↓

Crear Usuario

↓

Seleccionar Sucursal

↓

Asignar Grupo

↓

Guardar
3. Registro de clientes
Recepción

↓

Registrar Cliente

↓

Guardar Cliente
4. Venta de membresía
Recepción

↓

Seleccionar Cliente

↓

Seleccionar Membresía

↓

Registrar pago

↓

Crear ClienteMembresia
5. Registro de asistencia
Cliente llega

↓

Buscar Cliente

↓

Seleccionar Entrenamiento (Opcional)

↓

Registrar Entrada

↓

Crear Asistencia
6. Compras
Proveedor

↓

Compra

↓

CompraDetalle

↓

Actualizar InventarioSucursal
7. Ventas
Cliente

↓

Seleccionar Productos

↓

Venta

↓

VentaDetalle

↓

Actualizar InventarioSucursal
8. IA (Fase 2)
Cliente entra

↓

Selecciona Entrenamiento

↓

FastAPI

↓

Generar entrenamiento personalizado

↓

Enviar

PDF

Video

Telegram

App móvil
Relaciones generales
Plan
 │
 └──────────── Gym
                   │
        ┌──────────┴──────────┐
        │                     │
    Sucursal              Membresia
        │                     │
        │              ClienteMembresia
        │                     │
        │                 Cliente
        │                     │
        │                 Asistencia
        │                     │
        │              Entrenamiento
        │
        ├──────── User
        │
        ├──────── CategoriaProducto
        │              │
        │          Producto
        │              │
        │     InventarioSucursal
        │              │
        │      CompraDetalle
        │              │
        │          Compra
        │
        └──────── Venta
                     │
                VentaDetalle
Mi única recomendación antes de escribir código

Lo único que añadiría es un modelo abstracto base para todas las entidades del negocio, por ejemplo:

class GymModel(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

Así todos los modelos (Cliente, Producto, Proveedor, Membresia, Entrenamiento, etc.) heredan automáticamente estos campos. Obtienes consistencia, menos código repetido y una base mucho más fácil de mantener a medida que el proyecto crezca.