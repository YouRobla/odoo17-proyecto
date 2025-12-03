# API Gantt - Guía Completa para React

## 📋 Tabla de Contenidos

1. [Endpoint del Gantt](#endpoint-del-gantt)
2. [Tipos TypeScript](#tipos-typescript)
3. [Implementación del Gantt](#implementación-del-gantt)
4. [Visualización Proporcional de Reservas](#visualización-proporcional-de-reservas)
5. [Ejemplos de Código](#ejemplos-de-código)
6. [Casos de Uso](#casos-de-uso)

---

## Endpoint del Gantt

### GET /api/hotel/gantt/data

Obtiene datos completos del Gantt con información detallada de horas para reservas, optimizado para frontends React.

### Autenticación

Requiere API Key en el header:
```
X-API-Key: tu-api-key
```

### Parámetros de Consulta

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `target_date` | string | No | Fecha objetivo en formato `YYYY-MM-DD` (default: hoy) |
| `hotel_id` | int | No | ID del hotel para filtrar habitaciones |

### Ejemplo de Request

```typescript
const response = await fetch(
  'https://tu-servidor.com/api/hotel/gantt/data?target_date=2024-01-15&hotel_id=1',
  {
    method: 'GET',
    headers: {
      'X-API-Key': 'tu-api-key',
      'Content-Type': 'application/json',
    },
  }
);
```

---

## Tipos TypeScript

```typescript
// types/gantt.ts

export interface GanttReservation {
  id: number;
  booking_id: number;
  date_start: string; // ISO datetime: "2024-01-15T14:00:00"
  date_end: string; // ISO datetime: "2024-01-15T16:00:00"
  state: string;
  status_bar: string;
  customer_name: string;
  partner_id: number;
  room_id: [number, string]; // [id, name]
  room_name: string;
  total_amount: number;
  currency_symbol: string;
  discount_reason: string;
  
  // ⏰ Información completa de horas para reservas de pocas horas
  check_in_hour: number | null; // 0-23
  check_in_minute: number | null; // 0-59
  check_out_hour: number | null; // 0-23
  check_out_minute: number | null; // 0-59
  is_half_day_checkin: boolean;
  is_half_day_checkout: boolean;
  duration_hours: number | null; // Duración en horas (ej: 2.5 para 2 horas 30 min)
  duration_days: number | null; // Duración en días fraccionales (ej: 0.104 para 2.5 horas)
  
  // 📅 Información de la reserva principal (para referencia)
  booking_check_in: string;
  booking_check_out: string;
  booking_check_in_hour: number | null;
  booking_check_in_minute: number | null;
  booking_check_out_hour: number | null;
  booking_check_out_minute: number | null;
  booking_duration_hours: number | null;
  booking_duration_days: number | null;
  
  // 🔄 Cambios de habitación
  is_room_change?: boolean;
  is_new_reservation?: boolean;
  connected_booking_id?: number;
  is_room_change_origin?: boolean;
  is_room_change_destination?: boolean;
}

export interface GanttRoom {
  id: number;
  name: string;
  list_price: number;
  price: number;
  max_adult: number;
  max_child: number;
  capacity: number;
  hotel_id: [number, string] | false;
  room_type_id: number | false;
}

export interface MonthInfo {
  month_name: string;
  month_number: number;
  year: number;
  days: number[]; // [1, 2, 3, ..., 31]
  first_day: string; // ISO date
  last_day: string; // ISO date
  total_days: number;
}

export interface GanttMetadata {
  total_rooms: number;
  total_reservations: number;
  hotel_id: number | null;
  target_date: string;
  generated_at: string;
  timezone: string;
}

export interface GanttData {
  success: boolean;
  data: {
    rooms: GanttRoom[];
    reservations: GanttReservation[];
    month_info: MonthInfo;
    metadata: GanttMetadata;
  };
}
```

---

## Implementación del Gantt

### 1. Servicio API

```typescript
// services/ganttApi.ts
import { GanttData } from '../types/gantt';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://tu-servidor.com';
const API_KEY = process.env.REACT_APP_API_KEY || 'tu-api-key';

export async function fetchGanttData(
  targetDate?: string,
  hotelId?: number
): Promise<GanttData> {
  const params = new URLSearchParams();
  if (targetDate) params.append('target_date', targetDate);
  if (hotelId) params.append('hotel_id', hotelId.toString());

  const response = await fetch(
    `${API_BASE_URL}/api/hotel/gantt/data?${params.toString()}`,
    {
      method: 'GET',
      headers: {
        'X-API-Key': API_KEY,
        'Content-Type': 'application/json',
      },
    }
  );

  if (!response.ok) {
    throw new Error(`Error fetching Gantt data: ${response.statusText}`);
  }

  return response.json();
}
```

### 2. Utilidades para Cálculo de Posición

```typescript
// utils/ganttCalculations.ts
import { GanttReservation, MonthInfo } from '../types/gantt';

/**
 * Calcula la posición y ancho de una reserva en el Gantt
 * @param reservation - Reserva a calcular
 * @param monthInfo - Información del mes
 * @returns Objeto con left (%), width (%) y otros datos útiles
 */
export function calculateReservationPosition(
  reservation: GanttReservation,
  monthInfo: MonthInfo
): {
  left: number; // Porcentaje desde el inicio del mes
  width: number; // Porcentaje del ancho total
  startDay: number;
  endDay: number;
  startOffsetPercent: number; // Porcentaje dentro del día de inicio
  endOffsetPercent: number; // Porcentaje dentro del día de fin
} {
  const startDate = new Date(reservation.date_start);
  const endDate = new Date(reservation.date_end);
  
  // Obtener día del mes
  const startDay = startDate.getDate();
  const endDay = endDate.getDate();
  
  // Obtener información de horas (preferir datos del API)
  const checkInHour = reservation.check_in_hour ?? startDate.getHours();
  const checkInMinute = reservation.check_in_minute ?? startDate.getMinutes();
  const checkOutHour = reservation.check_out_hour ?? endDate.getHours();
  const checkOutMinute = reservation.check_out_minute ?? endDate.getMinutes();
  
  // Calcular porcentaje del día para inicio (0-100%)
  const startTotalMinutes = checkInHour * 60 + checkInMinute;
  const startOffsetPercent = (startTotalMinutes / 1440) * 100; // 1440 = minutos en un día
  
  // Calcular porcentaje del día para fin (0-100%)
  const endTotalMinutes = checkOutHour * 60 + checkOutMinute;
  const endOffsetPercent = (endTotalMinutes / 1440) * 100;
  
  // Calcular duración en días
  const duration = endDay - startDay;
  
  // Calcular ancho de cada día como porcentaje del mes
  const dayWidthPercent = 100 / monthInfo.total_days;
  
  // Calcular posición left: días antes + offset del primer día
  const daysBeforeStart = startDay - 1;
  const left = (daysBeforeStart * dayWidthPercent) + (startOffsetPercent * dayWidthPercent / 100);
  
  // Calcular ancho
  let width: number;
  if (duration === 0) {
    // Mismo día: ancho = diferencia de porcentajes
    width = (endOffsetPercent - startOffsetPercent) * dayWidthPercent / 100;
  } else {
    // Múltiples días
    const intermediateDaysWidth = duration * dayWidthPercent;
    const firstDayPartialWidth = (100 - startOffsetPercent) * dayWidthPercent / 100;
    const lastDayPartialWidth = endOffsetPercent * dayWidthPercent / 100;
    width = firstDayPartialWidth + intermediateDaysWidth + lastDayPartialWidth;
  }
  
  // Asegurar ancho mínimo (2% para visibilidad)
  const finalWidth = Math.max(width, 2);
  
  return {
    left,
    width: finalWidth,
    startDay,
    endDay,
    startOffsetPercent,
    endOffsetPercent,
  };
}

/**
 * Formatea la duración de una reserva
 * @param reservation - Reserva
 * @returns String formateado (ej: "2.5h", "30m", "1.5d")
 */
export function formatDuration(reservation: GanttReservation): string {
  // Preferir duration_hours del API si está disponible
  const hours = reservation.duration_hours ?? 
    (reservation.booking_duration_hours ?? null);
  
  if (hours === null) {
    // Fallback: calcular desde fechas
    const start = new Date(reservation.date_start);
    const end = new Date(reservation.date_end);
    const diffMs = end.getTime() - start.getTime();
    const hours = diffMs / (1000 * 60 * 60);
    
    return formatHours(hours);
  }
  
  return formatHours(hours);
}

function formatHours(hours: number): string {
  if (hours < 1) {
    // Menos de 1 hora: mostrar en minutos
    const minutes = Math.round(hours * 60);
    return `${minutes}m`;
  } else if (hours < 24) {
    // Menos de 24 horas: mostrar en horas
    return `${Math.round(hours * 10) / 10}h`;
  } else {
    // 24 horas o más: mostrar en días
    const days = hours / 24;
    return `${Math.round(days * 10) / 10}d`;
  }
}
```

### 3. Componente Gantt

```typescript
// components/GanttChart.tsx
import React, { useEffect, useState } from 'react';
import { fetchGanttData } from '../services/ganttApi';
import { calculateReservationPosition, formatDuration } from '../utils/ganttCalculations';
import { GanttData, GanttReservation } from '../types/gantt';
import './GanttChart.css';

const GanttChart: React.FC = () => {
  const [data, setData] = useState<GanttData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [targetDate, setTargetDate] = useState(
    new Date().toISOString().split('T')[0]
  );

  useEffect(() => {
    loadGanttData();
  }, [targetDate]);

  const loadGanttData = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await fetchGanttData(targetDate);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="gantt-loading">Cargando...</div>;
  if (error) return <div className="gantt-error">Error: {error}</div>;
  if (!data || !data.success) return null;

  const { rooms, reservations, month_info } = data.data;

  return (
    <div className="gantt-container">
      <div className="gantt-header">
        <h2>{month_info.month_name}</h2>
        <input
          type="date"
          value={targetDate}
          onChange={(e) => setTargetDate(e.target.value)}
        />
      </div>

      <div className="gantt-grid">
        {/* Header con días del mes */}
        <div className="gantt-header-row">
          <div className="gantt-room-header">Habitación</div>
          {month_info.days.map((day) => (
            <div key={day} className="gantt-day-header">
              {day}
            </div>
          ))}
        </div>

        {/* Filas de habitaciones */}
        {rooms.map((room) => {
          const roomReservations = reservations.filter(
            (res) => res.room_id[0] === room.id
          );

          return (
            <div key={room.id} className="gantt-row">
              <div className="gantt-room-name">{room.name}</div>
              <div className="gantt-cells" style={{ position: 'relative' }}>
                {/* Celdas del mes */}
                {month_info.days.map((day) => (
                  <div key={day} className="gantt-cell" />
                ))}

                {/* Barras de reserva */}
                {roomReservations.map((reservation) => {
                  const position = calculateReservationPosition(
                    reservation,
                    month_info
                  );

                  return (
                    <div
                      key={reservation.id}
                      className={`gantt-reservation-bar state-${reservation.state}`}
                      style={{
                        position: 'absolute',
                        left: `${position.left}%`,
                        width: `${position.width}%`,
                        top: '50%',
                        transform: 'translateY(-50%)',
                      }}
                      title={`${reservation.customer_name} - ${formatDuration(reservation)}`}
                    >
                      <span className="reservation-label">
                        {reservation.customer_name}
                      </span>
                      <span className="reservation-duration">
                        {formatDuration(reservation)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default GanttChart;
```

### 4. Estilos CSS

```css
/* components/GanttChart.css */
.gantt-container {
  width: 100%;
  overflow-x: auto;
  padding: 20px;
}

.gantt-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.gantt-grid {
  display: flex;
  flex-direction: column;
  border: 1px solid #ddd;
  border-radius: 4px;
  overflow: hidden;
}

.gantt-header-row {
  display: grid;
  grid-template-columns: 200px repeat(var(--days-in-month, 31), 1fr);
  background-color: #f5f5f5;
  border-bottom: 2px solid #ddd;
  position: sticky;
  top: 0;
  z-index: 10;
}

.gantt-room-header {
  padding: 12px;
  font-weight: bold;
  border-right: 1px solid #ddd;
}

.gantt-day-header {
  padding: 12px;
  text-align: center;
  border-right: 1px solid #ddd;
  font-weight: 600;
}

.gantt-row {
  display: grid;
  grid-template-columns: 200px 1fr;
  border-bottom: 1px solid #ddd;
  min-height: 60px;
}

.gantt-room-name {
  padding: 12px;
  border-right: 1px solid #ddd;
  background-color: #fafafa;
  font-weight: 500;
  display: flex;
  align-items: center;
}

.gantt-cells {
  display: grid;
  grid-template-columns: repeat(var(--days-in-month, 31), 1fr);
  position: relative;
  min-height: 60px;
}

.gantt-cell {
  border-right: 1px solid #ddd;
  background-color: #fff;
  min-width: 40px;
}

.gantt-reservation-bar {
  height: 24px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px;
  color: white;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  z-index: 2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gantt-reservation-bar:hover {
  transform: translateY(-50%) scale(1.05);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
}

.reservation-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reservation-duration {
  margin-left: 8px;
  background-color: rgba(0, 0, 0, 0.2);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
}

/* Estados de reserva */
.gantt-reservation-bar.state-confirmed {
  background: linear-gradient(135deg, #4CAF50, #45a049);
}

.gantt-reservation-bar.state-checkin,
.gantt-reservation-bar.state-check_in {
  background: linear-gradient(135deg, #2196F3, #1976D2);
}

.gantt-reservation-bar.state-checkout {
  background: linear-gradient(135deg, #FF9800, #F57C00);
}

.gantt-reservation-bar.state-cancelled {
  background: linear-gradient(135deg, #9E9E9E, #757575);
  opacity: 0.6;
}
```

---

## Visualización Proporcional de Reservas

### Cómo Funciona

El sistema calcula la posición y el ancho de cada reserva basándose en:

1. **Hora de inicio**: Determina dónde comienza la barra dentro de la celda
2. **Hora de fin**: Determina dónde termina la barra
3. **Duración**: Calcula el ancho proporcional

### Ejemplos Visuales

```
Reserva de 2 horas (14:00 - 16:00):
Celda del día 15:
[                    ]  ← Celda completa
[        ===         ]  ← Barra ocupa ~8.33% (2/24 horas)
         ↑
     14:00-16:00

Reserva de 6 horas (10:00 - 16:00):
[                    ]
[    ==========      ]  ← Barra ocupa ~25% (6/24 horas)
     ↑
  10:00-16:00

Reserva de 12 horas (08:00 - 20:00):
[                    ]
[  ==============    ]  ← Barra ocupa ~50% (12/24 horas)
   ↑
 08:00-20:00
```

### Cálculo de Posición

```typescript
// Ejemplo: Reserva de 2 horas (14:00 - 16:00) el día 15

// 1. Calcular offset de inicio
const startMinutes = 14 * 60 + 0 = 840 minutos
const startOffsetPercent = (840 / 1440) * 100 = 58.33%

// 2. Calcular offset de fin
const endMinutes = 16 * 60 + 0 = 960 minutos
const endOffsetPercent = (960 / 1440) * 100 = 66.67%

// 3. Calcular ancho
const dayWidthPercent = 100 / 31 = 3.23% (para enero)
const width = (66.67 - 58.33) * 3.23 / 100 = 0.27%

// 4. Calcular posición
const left = (15 - 1) * 3.23 + (58.33 * 3.23 / 100) = 45.21%
```

---

## Ejemplos de Código

### Ejemplo 1: Reserva de 2 horas

```typescript
const reservation: GanttReservation = {
  id: 123,
  date_start: "2024-01-15T14:00:00",
  date_end: "2024-01-15T16:00:00",
  check_in_hour: 14,
  check_in_minute: 0,
  check_out_hour: 16,
  check_out_minute: 0,
  duration_hours: 2.0,
  duration_days: 0.0833, // 2/24
  // ... otros campos
};

// Resultado visual:
// - Ocupa ~8.33% del ancho de la celda
// - Comienza a las 14:00 (58.33% del día)
// - Termina a las 16:00 (66.67% del día)
```

### Ejemplo 2: Reserva de medio día

```typescript
const reservation: GanttReservation = {
  id: 124,
  date_start: "2024-01-15T12:00:00",
  date_end: "2024-01-15T00:00:00", // Medianoche del día siguiente
  check_in_hour: 12,
  check_in_minute: 0,
  check_out_hour: 0,
  check_out_minute: 0,
  duration_hours: 12.0,
  duration_days: 0.5,
  is_half_day_checkin: true,
  // ... otros campos
};

// Resultado visual:
// - Ocupa 50% del ancho de la celda del día 15
// - Comienza al mediodía (50% del día)
```

---

## Casos de Uso

### 1. Reservas de Pocas Horas (2-6 horas)

Perfecto para:
- Reservas de día
- Reuniones cortas
- Uso temporal de habitaciones

**Características:**
- Se muestran proporcionalmente en la celda
- No bloquean todo el día
- Precio calculado por horas

### 2. Reservas de Medio Día

Perfecto para:
- Check-in tarde / Check-out temprano
- Reservas de 12 horas

**Características:**
- Ocupan la mitad de la celda
- Permiten disponibilidad en la otra mitad del día

### 3. Reservas de Día Completo

**Características:**
- Ocupan toda la celda
- Bloquean el día completo

---

## Respuesta del API - Ejemplo Completo

```json
{
  "success": true,
  "data": {
    "rooms": [
      {
        "id": 1,
        "name": "Habitación 101",
        "price": 100.0,
        "capacity": 3,
        "hotel_id": [1, "Hotel Central"]
      }
    ],
    "reservations": [
      {
        "id": 123,
        "booking_id": 45,
        "date_start": "2024-01-15T14:00:00",
        "date_end": "2024-01-15T16:00:00",
        "state": "confirmed",
        "customer_name": "Juan Pérez",
        "room_id": [1, "Habitación 101"],
        "check_in_hour": 14,
        "check_in_minute": 0,
        "check_out_hour": 16,
        "check_out_minute": 0,
        "is_half_day_checkin": true,
        "is_half_day_checkout": false,
        "duration_hours": 2.0,
        "duration_days": 0.0833,
        "total_amount": 8.33,
        "currency_symbol": "$"
      }
    ],
    "month_info": {
      "month_name": "Enero 2024",
      "month_number": 1,
      "year": 2024,
      "days": [1, 2, 3, ..., 31],
      "total_days": 31
    },
    "metadata": {
      "total_rooms": 10,
      "total_reservations": 25,
      "hotel_id": 1,
      "target_date": "2024-01-15",
      "generated_at": "2024-01-15T10:30:00",
      "timezone": "America/Lima"
    }
  }
}
```

---

## ✅ Verificación de Endpoints

El endpoint `/api/hotel/gantt/data` expone **TODA** la información necesaria para reservas de pocas horas:

- ✅ `check_in_hour` y `check_in_minute` - Hora exacta de inicio
- ✅ `check_out_hour` y `check_out_minute` - Hora exacta de fin
- ✅ `duration_hours` - Duración en horas (precisión decimal)
- ✅ `duration_days` - Duración en días fraccionales
- ✅ `is_half_day_checkin` y `is_half_day_checkout` - Flags para medio día
- ✅ `date_start` y `date_end` - Fechas completas ISO datetime
- ✅ Información de la reserva principal y de la línea específica

**El API está completamente preparado para reservas de pocas horas.**

---

## 🔄 Endpoint de Cambio de Habitación

### POST /api/hotel/reserva/<booking_id>/change_room

Permite cambiar la habitación de una reserva existente, con soporte completo para horas específicas.

### Autenticación

Requiere API Key en el header:
```
X-API-Key: tu-api-key
```

### Parámetros del Body (JSON)

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `booking_line_id` | int | No* | ID de la línea de reserva (requerido si la reserva tiene múltiples líneas) |
| `new_room_id` | int | Sí | ID de la nueva habitación |
| `change_start_date` | string | Sí** | Fecha de inicio del cambio (formato: `YYYY-MM-DD` o `YYYY-MM-DD HH:MM:SS`) |
| `change_end_date` | string | Sí** | Fecha de fin del cambio (formato: `YYYY-MM-DD` o `YYYY-MM-DD HH:MM:SS`) |
| `change_start_datetime` | string | Sí** | DateTime de inicio (formato ISO: `YYYY-MM-DDTHH:MM:SS`) - alternativa a `change_start_date` |
| `change_end_datetime` | string | Sí** | DateTime de fin (formato ISO: `YYYY-MM-DDTHH:MM:SS`) - alternativa a `change_end_date` |
| `check_in_hour` | int | No | Hora de check-in (0-23) - se combina con `change_start_date` si se proporciona |
| `check_in_minute` | int | No | Minuto de check-in (0-59) - se combina con `change_start_date` si se proporciona |
| `check_out_hour` | int | No | Hora de check-out (0-23) - se combina con `change_end_date` si se proporciona |
| `check_out_minute` | int | No | Minuto de check-out (0-59) - se combina con `change_end_date` si se proporciona |
| `use_custom_price` | bool | No | Si se usa precio personalizado (default: false) |
| `custom_price` | float | No | Precio personalizado por noche (requerido si `use_custom_price=true`) |
| `note` | string | No | Notas o razón del cambio |

**Notas:**
- * `booking_line_id` es requerido solo si la reserva tiene múltiples líneas de habitación
- ** Debe proporcionar `change_start_date`/`change_start_datetime` y `change_end_date`/`change_end_datetime`
- **Prioridad de horas:** Si se proporcionan `check_in_hour`/`check_in_minute` con `change_start_date`, se usarán esas horas. Si no, se usarán las horas del datetime si está incluido, o las horas de la reserva original.
- Si se proporcionan horas separadas (`check_in_hour`, `check_in_minute`, etc.) junto con una fecha, se combinarán para crear el datetime completo.

### Formatos de Fecha/Hora Aceptados

El endpoint acepta múltiples formatos:

1. **Solo fecha** (sin hora):
   ```json
   "change_start_date": "2024-01-15"
   ```
   - Se usarán las horas de la reserva original

2. **Fecha con hora** (formato estándar):
   ```json
   "change_start_date": "2024-01-15 14:00:00"
   ```

3. **DateTime ISO** (formato estándar):
   ```json
   "change_start_datetime": "2024-01-15T14:00:00"
   ```

4. **Fecha + Horas Separadas** (NUEVO - Recomendado para mayor flexibilidad):
   ```json
   {
     "change_start_date": "2024-01-15",
     "check_in_hour": 14,
     "check_in_minute": 30,
     "change_end_date": "2024-01-20",
     "check_out_hour": 11,
     "check_out_minute": 0
   }
   ```
   - Permite especificar fecha y hora por separado
   - Útil cuando el frontend maneja horas independientemente de las fechas

### Ejemplo de Request

#### Ejemplo 1: Cambio con horas específicas

```typescript
const response = await fetch(
  `https://tu-servidor.com/api/hotel/reserva/${bookingId}/change_room`,
  {
    method: 'POST',
    headers: {
      'X-API-Key': 'tu-api-key',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      booking_line_id: 123,
      new_room_id: 45,
      change_start_datetime: '2024-01-15T14:30:00',  // Cambio a las 14:30
      change_end_datetime: '2024-01-20T11:00:00',    // Hasta las 11:00
      use_custom_price: false,
      note: 'Cambio solicitado por el huésped'
    })
  }
);

const data = await response.json();
```

#### Ejemplo 2: Cambio solo con fechas (usa horas de la reserva original)

```typescript
const response = await fetch(
  `https://tu-servidor.com/api/hotel/reserva/${bookingId}/change_room`,
  {
    method: 'POST',
    headers: {
      'X-API-Key': 'tu-api-key',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      new_room_id: 45,
      change_start_date: '2024-01-15',  // Sin hora - usará hora de check_in original
      change_end_date: '2024-01-20',     // Sin hora - usará hora de check_out original
    })
  }
);
```

#### Ejemplo 3: Cambio con fechas y horas separadas (NUEVO)

```typescript
const response = await fetch(
  `https://tu-servidor.com/api/hotel/reserva/${bookingId}/change_room`,
  {
    method: 'POST',
    headers: {
      'X-API-Key': 'tu-api-key',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      booking_line_id: 123,
      new_room_id: 45,
      change_start_date: '2024-01-15',
      check_in_hour: 14,        // Hora separada
      check_in_minute: 30,      // Minuto separado
      change_end_date: '2024-01-20',
      check_out_hour: 11,      // Hora separada
      check_out_minute: 0,      // Minuto separado
      use_custom_price: false,
      note: 'Cambio con horas específicas'
    })
  }
);
```

### Respuesta Exitosa

```json
{
  "success": true,
  "message": "Cambio de habitación aplicado correctamente.",
  "data": {
    "reserva_id": 123,
    "action": {
      "type": "ir.actions.act_window",
      "res_model": "hotel.booking",
      "res_id": 124,
      "domain": [["id", "in", [124]]]
    },
    "new_reserva": {
      "id": 124,
      "sequence_id": "BOOK-002",
      "check_in": "2024-01-15 14:30:00",
      "check_out": "2024-01-20 11:00:00",
      "check_in_hour": 14,
      "check_in_minute": 30,
      "check_out_hour": 11,
      "check_out_minute": 0,
      "status_bar": "confirmed"
    }
  }
}
```

### Campos de la Respuesta

- `reserva_id`: ID de la reserva original
- `action`: Información de la acción ejecutada (puede contener `res_id` de la nueva reserva)
- `new_reserva`: Objeto con información de la nueva reserva creada (si está disponible):
  - `id`: ID de la nueva reserva
  - `sequence_id`: Número de secuencia de la reserva
  - `check_in`: DateTime completo de check-in
  - `check_out`: DateTime completo de check-out
  - `check_in_hour`: Hora de check-in (0-23)
  - `check_in_minute`: Minuto de check-in (0-59)
  - `check_out_hour`: Hora de check-out (0-23)
  - `check_out_minute`: Minuto de check-out (0-59)
  - `status_bar`: Estado de la nueva reserva

### TypeScript Interface

```typescript
interface ChangeRoomRequest {
  booking_line_id?: number;
  new_room_id: number;
  change_start_date?: string;  // "YYYY-MM-DD" o "YYYY-MM-DD HH:MM:SS"
  change_end_date?: string;     // "YYYY-MM-DD" o "YYYY-MM-DD HH:MM:SS"
  change_start_datetime?: string; // "YYYY-MM-DDTHH:MM:SS"
  change_end_datetime?: string;   // "YYYY-MM-DDTHH:MM:SS"
  check_in_hour?: number;          // 0-23 (se combina con change_start_date)
  check_in_minute?: number;        // 0-59 (se combina con change_start_date)
  check_out_hour?: number;         // 0-23 (se combina con change_end_date)
  check_out_minute?: number;       // 0-59 (se combina con change_end_date)
  use_custom_price?: boolean;
  custom_price?: number;
  note?: string;
}

interface ChangeRoomResponse {
  success: boolean;
  message: string;
  data: {
    reserva_id: number;
    action: {
      type: string;
      res_model: string;
      res_id?: number;
      domain?: any[];
    };
    new_reserva?: {
      id: number;
      sequence_id: string;
      check_in: string;
      check_out: string;
      check_in_hour: number | null;
      check_in_minute: number | null;
      check_out_hour: number | null;
      check_out_minute: number | null;
      status_bar: string;
    };
  };
}
```

### Notas Importantes

1. **Horas Específicas**: Si necesitas cambiar a horas diferentes a las de la reserva original, siempre usa `change_start_datetime` y `change_end_datetime` con formato ISO.

2. **Compatibilidad**: El endpoint es retrocompatible - si solo envías fechas sin horas, usará las horas de la reserva original.

3. **Nueva Reserva**: El cambio de habitación crea una nueva reserva conectada a la original. La respuesta incluye información de la nueva reserva con las horas exactas aplicadas.

4. **Validación**: El sistema valida que:
   - La nueva habitación esté disponible en el período especificado
   - Las fechas sean válidas
   - El cambio no viole reglas de negocio
