# Hotel Management System - Gantt de Reservas

Este módulo implementa un sistema de gestión hotelera con una vista Gantt interactiva para la visualización y gestión de reservas.

## Arquitectura General

- **Backend (Odoo Python):**
  - El modelo principal es `hotel.booking`, que gestiona las reservas y su estado (`status_bar`: initial, confirm, allot, cancel, checkout).
  - Los endpoints y métodos del backend exponen los datos de reservas y habitaciones a través de RPC para el frontend.
  - Los estados de reserva están alineados con la lógica de negocio hotelera (por noches, no por horas).

- **Frontend (Owl JS):**
  - El componente principal es `reservation_gantt.js`.
  - Utiliza Owl y Luxon para renderizar la grilla, gestionar el estado y manipular fechas.
  - La grilla muestra habitaciones en filas y días del mes en columnas.
  - Las reservas se visualizan como barras que cubren desde el día de check-in hasta el día anterior al check-out.
  - El usuario puede seleccionar celdas para crear nuevas reservas, filtrando por tipo de habitación, mes y orden.
  - El tooltip profesional muestra información relevante de la reserva al pasar el mouse.
  - Los colores de las barras y la leyenda están alineados con los estados del backend.

- **Estilos (SCSS):**
  - Los estilos están modularizados y usan variables para colores de estado.
  - El Gantt es responsive y accesible.
  - El tooltip es moderno, con sombra, bordes redondeados y fuente clara.
  - Las barras de reserva tienen animaciones suaves y colores accesibles.

## Lógica de Selección y Creación de Reservas

- El usuario puede seleccionar un rango de días en una habitación disponible.
- Al soltar el mouse, se abre el formulario de nueva reserva con el rango seleccionado y la hora actual como hora por defecto.
- El check-in es el primer día seleccionado, el check-out es el día siguiente al último seleccionado.
- La reserva se crea con el formato de fecha/hora que Odoo espera (`YYYY-MM-DD HH:mm:ss`).
- No se permite seleccionar días ocupados ni pasados.

## Flujo de Datos

1. El frontend solicita los datos de habitaciones y reservas al backend vía RPC.
2. El usuario interactúa con la grilla para filtrar, seleccionar o crear reservas.
3. Al crear una reserva, el frontend envía los datos al backend, que los valida y almacena.
4. Los cambios se reflejan en tiempo real en la vista Gantt.

## Personalización

- Los colores de estado pueden personalizarse en `reservation_gantt.js` y en el SCSS.
- El tooltip puede ampliarse para mostrar más información si se requiere.
- El rango de meses visibles y los filtros pueden ajustarse fácilmente.

## Consideraciones de Seguridad

- No se usa `t-raw` con datos de usuario; el tooltip se renderiza con Owl y `t-esc`.
- No se exponen datos sensibles en el DOM.
- Los datos se validan antes de operar sobre ellos.
- El código es accesible y cumple buenas prácticas de frontend y backend.

## Mejores Prácticas Aplicadas

- Código modular y comentado.
- Separación clara entre lógica de negocio, presentación y estilos.
- Accesibilidad y responsividad en la UI.
- Seguridad en el manejo de datos y eventos.

---

Para cualquier personalización avanzada o integración con otros módulos, consulta la documentación interna del código y sigue las mejores prácticas de Odoo y Owl.


