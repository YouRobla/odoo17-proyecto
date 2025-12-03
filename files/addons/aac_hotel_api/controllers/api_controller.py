import json
import logging
import base64
from datetime import datetime, timedelta
from functools import wraps
from odoo import http, fields, _
from odoo.http import request, Response
from odoo.tools import json_default
from odoo.exceptions import ValidationError, AccessError, UserError, MissingError
from .api_auth import validate_api_key

_logger = logging.getLogger(__name__)

# Constantes
MAX_FILE_SIZE_MB = 10
MAX_STAY_DAYS = 365
MIN_AGE = 1
MAX_AGE = 120
ADULT_AGE_THRESHOLD = 18

VALID_STATUSES = [
    'initial', 'draft', 'confirmed', 'checkin', 'checkout', 
    'cleaning_needed', 'room_ready', 'cancelled', 'no_show',
    'allot', 'check_in', 'pending', 'checkout_pending'
]

TERMINAL_STATUSES = ['cancelled', 'checkout', 'no_show']

VALID_BOOKING_REFERENCES = ['sale_order', 'manual', 'agent', 'other']

VALID_GENDERS = ['male', 'female', 'other']

VALID_COMMISSION_TYPES = ['fixed', 'percentage']

STATUS_TRANSITIONS = {
    'initial': ['confirmed', 'cancelled'],
    'draft': ['confirmed', 'cancelled'],
    'confirmed': ['checkin', 'check_in', 'cancelled', 'no_show'],
    'checkin': ['checkout', 'cancelled'],
    'check_in': ['checkout', 'cancelled'],
    'checkout': ['cleaning_needed'],
    'cleaning_needed': ['room_ready'],
    'room_ready': ['confirmed'],
    'cancelled': ['initial'],
    'no_show': ['initial'],
    'allot': ['checkin', 'check_in', 'cancelled', 'no_show'],
    'pending': ['confirmed', 'cancelled']
}


def handle_api_errors(func):
    """Decorador para manejo centralizado de errores en endpoints"""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except ValueError as e:
            _logger.warning("Error de validación en %s: %s", func.__name__, str(e))
            return self._prepare_response({
                'success': False,
                'error': str(e)
            }, status=400)
        except (AccessError, MissingError) as e:
            _logger.warning("Error de acceso en %s: %s", func.__name__, str(e))
            return self._prepare_response({
                'success': False,
                'error': 'No tiene permisos para acceder a esta información'
            }, status=403)
        except UserError as e:
            _logger.warning("Error de usuario en %s: %s", func.__name__, str(e))
            return self._prepare_response({
                'success': False,
                'error': str(e)
            }, status=400)
        except Exception as e:
            _logger.exception("Error inesperado en %s: %s", func.__name__, str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)
    return wrapper


class HotelApiController(http.Controller):

    def _prepare_response(self, data, status=200):
        """Preparar respuesta HTTP con formato JSON"""
        return Response(
            json.dumps(data, default=json_default),
            status=status,
            content_type='application/json'
        )

    def _check_access_rights(self, model_name, operation='read', raise_exception=True):
        """
        Verificar permisos de acceso a un modelo.
        
        Args:
            model_name: Nombre del modelo (ej: 'hotel.booking')
            operation: Operación a verificar ('read', 'write', 'create', 'unlink')
            raise_exception: Si True, lanza AccessError si no hay permisos
        
        Returns:
            bool: True si tiene permisos, False en caso contrario (solo si raise_exception=False)
        """
        try:
            if not request.env:
                error_msg = "El entorno de la solicitud no está disponible. Asegúrese de usar el decorador @validate_api_key"
                _logger.error(error_msg)
                if raise_exception:
                    raise AccessError(error_msg)
                return False
            
            model = request.env[model_name]
            model.check_access_rights(operation, raise_exception=True)
            return True
        except AccessError as e:
            if raise_exception:
                _logger.warning(f"Error de acceso a {model_name} ({operation}): {str(e)}")
                raise
            return False

    def _check_access_rule(self, recordset, operation='read', raise_exception=True):
        """
        Verificar reglas de acceso para un recordset específico.
        
        Args:
            recordset: Recordset de Odoo
            operation: Operación a verificar ('read', 'write', 'create', 'unlink')
            raise_exception: Si True, lanza AccessError si no hay permisos
        
        Returns:
            bool: True si tiene permisos, False en caso contrario (solo si raise_exception=False)
        """
        try:
            if not recordset:
                return True
            # En Odoo 17, check_access_rule() solo acepta 'operation', no 'raise_exception'
            recordset.check_access_rule(operation)
            return True
        except AccessError as e:
            if raise_exception:
                _logger.warning(f"Error de regla de acceso ({operation}): {str(e)}")
                raise
            return False

    def _ensure_access(self, recordset, operation='read'):
        """
        Asegurar que el usuario tiene acceso al recordset.
        Si no tiene permisos, intenta usar sudo() solo si es necesario,
        pero registra la acción en los logs.
        
        Args:
            recordset: Recordset de Odoo
            operation: Operación a verificar
        
        Returns:
            Recordset: El recordset con permisos adecuados
        """
        try:
            self._check_access_rights(recordset._name, operation)
            self._check_access_rule(recordset, operation)
            return recordset
        except AccessError:
            # Si el usuario no tiene permisos, verificar si puede usar sudo()
            # solo para operaciones de lectura
            if operation == 'read' and request.env.user.has_group('base.group_system'):
                _logger.info(
                    f"Usuario {request.env.user.login} usando sudo() para lectura de {recordset._name}"
                )
                return recordset.sudo()
            raise

    def _parse_json_data(self):
        """Parsear datos JSON de la petición"""
        try:
            data = request.httprequest.data
            if not data:
                # Si no hay datos, retornar diccionario vacío
                return {}
            return json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f'Formato JSON inválido: {str(e)}')
    
    def _parse_request_data(self):
        """
        Parsear datos de la petición, soportando tanto JSON como form-data
        Retorna un diccionario con los datos parseados
        """
        content_type = request.httprequest.content_type or ''
        
        _logger.info("Content-Type recibido: %s", content_type)
        _logger.info("Tiene form: %s", hasattr(request.httprequest, 'form'))
        _logger.info("Tiene files: %s", hasattr(request.httprequest, 'files'))
        _logger.info("Datos raw: %s", len(request.httprequest.data) if request.httprequest.data else 0)
        
        # Detectar form-data: si tiene form o files, es form-data
        has_form = hasattr(request.httprequest, 'form') and request.httprequest.form
        has_files = hasattr(request.httprequest, 'files') and request.httprequest.files
        is_multipart = 'multipart/form-data' in content_type or 'form-data' in content_type
        
        # Si es form-data o multipart/form-data, o si tiene form/files
        if is_multipart or has_form or has_files:
            data = {}
            
            # Procesar campos de formulario (texto)
            # En Werkzeug, los datos de form vienen en request.httprequest.form (ImmutableMultiDict)
            try:
                # Obtener todos los campos del formulario
                form_dict = dict(request.httprequest.form) if hasattr(request.httprequest, 'form') else {}
                _logger.info("Campos del formulario recibidos: %s", list(form_dict.keys()))
                
                for key, value in form_dict.items():
                    _logger.info("Procesando campo form-data: %s = %s", key, value[:100] if isinstance(value, str) and len(value) > 100 else value)
                    if key == 'documents':
                        # Si documents viene como string JSON, parsearlo
                        try:
                            parsed_value = json.loads(value) if isinstance(value, str) else value
                            if isinstance(parsed_value, list):
                                data[key] = parsed_value
                                _logger.info("Documents parseado como JSON array: %s", data[key])
                            elif isinstance(parsed_value, dict):
                                data[key] = [parsed_value]  # Convertir objeto único a array
                                _logger.info("Documents parseado como JSON objeto, convertido a array: %s", data[key])
                            else:
                                data[key] = parsed_value
                                _logger.info("Documents parseado: %s", data[key])
                        except json.JSONDecodeError as e:
                            # Si no es JSON válido, ignorar y dejar que los archivos creen los documentos
                            _logger.warning("Documents no es JSON válido (%s), se ignorará y se crearán desde archivos", str(e))
                            # No agregar documents al data, dejar que se cree desde los archivos
                    else:
                        data[key] = value
                        _logger.info("Campo agregado: %s = %s", key, value)
            except Exception as e:
                _logger.error("Error procesando form-data: %s", str(e))
            
            # Procesar archivos
            try:
                files_dict = dict(request.httprequest.files) if hasattr(request.httprequest, 'files') else {}
                _logger.info("Archivos recibidos: %s", list(files_dict.keys()))
                
                if files_dict:
                    documents = data.get('documents', [])
                    if not isinstance(documents, list):
                        documents = []
                    
                    # Convertir archivos a base64 y agregarlos a documents
                    for file_key, file_obj in files_dict.items():
                        _logger.info("Procesando archivo: %s", file_key)
                        if file_obj and hasattr(file_obj, 'filename') and file_obj.filename:
                            _logger.info("Archivo encontrado: %s (tamaño: %s bytes)", file_obj.filename, getattr(file_obj, 'content_length', 'desconocido'))
                            # Leer el archivo y convertirlo a base64
                            file_obj.seek(0)  # Asegurar que estamos al inicio del archivo
                            file_content = file_obj.read()
                            file_base64 = base64.b64encode(file_content).decode('utf-8')
                            _logger.info("Archivo convertido a base64: %s caracteres", len(file_base64))
                            
                            # Si ya hay un documento en documents con el mismo nombre, usar ese
                            # Si no, crear uno nuevo
                            doc_found = False
                            for doc in documents:
                                if isinstance(doc, dict) and doc.get('file_name') == file_obj.filename:
                                    doc['file'] = file_base64
                                    doc_found = True
                                    _logger.info("Archivo agregado a documento existente: %s", file_obj.filename)
                                    break
                            
                            if not doc_found:
                                # Crear nuevo documento
                                doc_data = {
                                    'name': file_obj.filename.rsplit('.', 1)[0] if '.' in file_obj.filename else file_obj.filename,
                                    'file_name': file_obj.filename,
                                    'file': file_base64
                                }
                                documents.append(doc_data)
                                _logger.info("Nuevo documento creado: %s", doc_data['name'])
                    
                    if documents:
                        data['documents'] = documents
                        _logger.info("Total documentos procesados: %d", len(documents))
            except Exception as e:
                _logger.error("Error procesando archivos: %s", str(e))
            
            _logger.info("Datos finales parseados: %s", {k: (v[:100] if isinstance(v, str) and len(v) > 100 else v) for k, v in data.items()})
            return data
        else:
            # JSON normal - pero solo si hay datos
            if request.httprequest.data and len(request.httprequest.data) > 0:
                _logger.info("Parseando como JSON")
                return self._parse_json_data()
            else:
                # Si no hay datos, retornar diccionario vacío
                _logger.warning("No se detectó form-data ni hay datos JSON, retornando diccionario vacío")
                return {}

    def _parse_datetime(self, date_str, field_name='fecha'):
        """Parsear string a datetime con manejo de errores mejorado"""
        if not date_str:
            raise ValueError(f'{field_name} es requerida')
        
        try:
            if isinstance(date_str, str):
                # Soportar múltiples formatos
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                    try:
                        return datetime.strptime(date_str.replace('T', ' '), fmt)
                    except ValueError:
                        continue
                raise ValueError(f'Formato de {field_name} no reconocido')
            return date_str
        except Exception as e:
            raise ValueError(f'Error al procesar {field_name}: {str(e)}')

    def _validate_partner_id(self, partner_id_str):
        """Validar que el partner_id sea un número entero válido y exista"""
        try:
            partner_id = int(partner_id_str)
            partner = request.env['res.partner'].browse(partner_id)
            if not partner.exists():
                raise ValueError(f'El partner con ID {partner_id} no existe')
            return partner_id
        except (ValueError, TypeError):
            raise ValueError('El partner_id debe ser un número entero válido')

    def _validate_dates(self, check_in_str, check_out_str):
        """Validar fechas de check-in y check-out con lógica mejorada"""
        check_in = self._parse_datetime(check_in_str, 'check_in')
        check_out = self._parse_datetime(check_out_str, 'check_out')
        
        # Validar que check_out sea posterior o igual a check_in (permitir mismo día)
        if check_out < check_in:
            raise ValueError('La fecha de check-out no puede ser anterior a la fecha de check-in')
        
        # Validar que check_in no sea en el pasado
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if check_in.date() < today.date():
            raise ValueError('La fecha de check-in no puede ser en el pasado')
        
        # Validar duración máxima de estadía
        days_diff = (check_out.date() - check_in.date()).days
        if days_diff > MAX_STAY_DAYS:
            raise ValueError(f'La estadía no puede ser mayor a {MAX_STAY_DAYS} días')
        
        # Permitir reservas de 0 días (mismo día - uso diurno) o más
        # El sistema automáticamente asignará mínimo 1 día para visualización en Gantt
        
        return check_in, check_out

    def _validate_rooms_data(self, rooms_data):
        """Validar datos de habitaciones con verificación de existencia"""
        if not rooms_data or len(rooms_data) == 0:
            raise ValueError('Debe especificar al menos una habitación')
        
        for i, room in enumerate(rooms_data, start=1):
            product_id = room.get('product_id') or room.get('room_id')
            
            if not product_id:
                raise ValueError(f'Habitación {i}: Debe especificar el ID del producto (product_id o room_id)')
            
            try:
                product_id = int(product_id)
            except (ValueError, TypeError):
                raise ValueError(f'Habitación {i}: El product_id debe ser un número válido')
            
            # Validar existencia y tipo de producto
            product = request.env['product.product'].browse(product_id)
            if not product.exists():
                raise ValueError(f'Habitación {i}: El producto con ID {product_id} no existe')
            
            if not product.is_room_type:
                raise ValueError(f'Habitación {i}: El producto "{product.name}" no es un tipo de habitación')
            
            # Validar precio si se proporciona
            if room.get('price') is not None:
                try:
                    price = float(room['price'])
                    if price < 0:
                        raise ValueError(f'Habitación {i}: El precio no puede ser negativo')
                except (ValueError, TypeError):
                    raise ValueError(f'Habitación {i}: El precio debe ser un número válido')
            
            # Validar descuento si se proporciona
            if room.get('discount') is not None:
                try:
                    discount = float(room['discount'])
                    if discount < 0 or discount > 100:
                        raise ValueError(f'Habitación {i}: El descuento debe estar entre 0 y 100')
                except (ValueError, TypeError):
                    raise ValueError(f'Habitación {i}: El descuento debe ser un número válido')
            
            # Validar huéspedes si se proporcionan
            if room.get('guests'):
                self._validate_guests_data(room['guests'], i)

    def _validate_guests_data(self, guests_data, room_number):
        """Validar datos de huéspedes con contadores"""
        if not guests_data or len(guests_data) == 0:
            raise ValueError(f'Habitación {room_number}: Debe especificar al menos un huésped')
        
        adult_count = 0
        child_count = 0
        
        for i, guest in enumerate(guests_data, start=1):
            # Validar nombre o partner_id
            if not guest.get('name') and not guest.get('partner_id'):
                raise ValueError(
                    f'Habitación {room_number}, Huésped {i}: '
                    f'Debe especificar el nombre o un partner_id'
                )
            
            # Validar partner_id si se proporciona
            if guest.get('partner_id'):
                partner = request.env['res.partner'].browse(guest['partner_id'])
                if not partner.exists():
                    raise ValueError(
                        f'Habitación {room_number}, Huésped {i}: '
                        f'El partner con ID {guest["partner_id"]} no existe'
                    )
            
            # Validar edad
            if not guest.get('age'):
                raise ValueError(f'Habitación {room_number}, Huésped {i}: Debe especificar la edad')
            
            try:
                age = int(guest['age'])
                if age < MIN_AGE:
                    raise ValueError(
                        f'Habitación {room_number}, Huésped {i}: '
                        f'La edad debe ser mayor a {MIN_AGE - 1}'
                    )
                if age > MAX_AGE:
                    raise ValueError(
                        f'Habitación {room_number}, Huésped {i}: '
                        f'La edad no puede ser mayor a {MAX_AGE} años'
                    )
            except (ValueError, TypeError):
                raise ValueError(
                    f'Habitación {room_number}, Huésped {i}: '
                    f'La edad debe ser un número válido'
                )
            
            # Contar adultos y niños
            if age >= ADULT_AGE_THRESHOLD:
                adult_count += 1
            else:
                child_count += 1
            
            # Validar género
            if guest.get('gender') and guest['gender'] not in VALID_GENDERS:
                raise ValueError(
                    f'Habitación {room_number}, Huésped {i}: '
                    f'Género inválido. Debe ser: {", ".join(VALID_GENDERS)}'
                )
        
        # Validar que haya al menos un adulto por habitación
        if adult_count == 0:
            raise ValueError(f'Habitación {room_number}: Debe haber al menos un adulto por habitación')

    def _validate_booking_status(self, status):
        """Validar estado de reserva"""
        if status and status not in VALID_STATUSES:
            raise ValueError(
                f'Estado inválido: {status}. Estados válidos: {", ".join(VALID_STATUSES)}'
            )

    def _validate_documents_data(self, documents_data):
        """Validar datos de documentos con límite de tamaño"""
        if not documents_data:
            return
        
        for i, doc in enumerate(documents_data, start=1):
            if not doc.get('name'):
                raise ValueError(f'Documento {i}: Debe especificar el nombre del documento')
            
            # Validar tamaño del archivo
            if doc.get('file'):
                try:
                    file_data = base64.b64decode(doc['file'])
                    file_size_mb = len(file_data) / (1024 * 1024)
                    
                    if file_size_mb > MAX_FILE_SIZE_MB:
                        raise ValueError(
                            f'Documento {i}: El archivo no puede ser mayor a {MAX_FILE_SIZE_MB}MB'
                        )
                except Exception:
                    raise ValueError(f'Documento {i}: Formato de archivo inválido (debe ser base64)')

    def _validate_hotel_id(self, hotel_id):
        """Validar que el hotel existe"""
        if not hotel_id:
            raise ValueError('El hotel_id es requerido')
        try:
            hotel_id = int(hotel_id)
            hotel = request.env['hotel.hotels'].browse(hotel_id)
            if not hotel.exists():
                raise ValueError(f'El hotel con ID {hotel_id} no existe')
            return hotel_id
        except (ValueError, TypeError) as e:
            if isinstance(e, ValueError) and 'hotel_id' in str(e).lower():
                raise
            raise ValueError('El hotel_id debe ser un número entero válido')

    def _validate_booking_reference(self, booking_reference):
        """Validar referencia de reserva"""
        if booking_reference and booking_reference not in VALID_BOOKING_REFERENCES:
            raise ValueError(
                f'Referencia de reserva inválida: {booking_reference}. '
                f'Referencias válidas: {", ".join(VALID_BOOKING_REFERENCES)}'
            )

    def _validate_agent_data(self, data):
        """Validar datos de agente con reglas de negocio"""
        if not data.get('via_agent'):
            return
        
        if not data.get('agent_id'):
            raise ValueError('Debe especificar el agente cuando via_agent es True')
        
        agent = request.env['res.partner'].browse(data['agent_id'])
        if not agent.exists():
            raise ValueError(f'El agente con ID {data["agent_id"]} no existe')
        
        commission_type = data.get('commission_type')
        if commission_type:
            if commission_type not in VALID_COMMISSION_TYPES:
                raise ValueError(
                    f'Tipo de comisión debe ser: {", ".join(VALID_COMMISSION_TYPES)}'
                )
            
            if commission_type == 'fixed':
                if not data.get('agent_commission_amount'):
                    raise ValueError('Debe especificar el monto de comisión fija')
                
                try:
                    amount = float(data['agent_commission_amount'])
                    if amount < 0:
                        raise ValueError('El monto de comisión no puede ser negativo')
                except (ValueError, TypeError):
                    raise ValueError('El monto de comisión debe ser un número válido')
            
            if commission_type == 'percentage':
                if not data.get('agent_commission_percentage'):
                    raise ValueError('Debe especificar el porcentaje de comisión')
                
                try:
                    percentage = float(data['agent_commission_percentage'])
                    if percentage < 0 or percentage > 100:
                        raise ValueError('El porcentaje de comisión debe estar entre 0 y 100')
                except (ValueError, TypeError):
                    raise ValueError('El porcentaje de comisión debe ser un número válido')

    def _validate_booking_for_update(self, booking, data):
        """Validar reserva para actualización con verificación de estado"""
        if booking.status_bar in TERMINAL_STATUSES:
            raise ValueError(
                f'No se puede actualizar una reserva en estado "{booking.status_bar}"'
            )
        
        if 'status_bar' in data:
            self._validate_status_transition(booking.status_bar, data['status_bar'])

    def _validate_status_transition(self, current_status, new_status):
        """Validar transición de estado con reglas de negocio"""
        allowed_transitions = STATUS_TRANSITIONS.get(current_status, [])
        
        # Normalizar checkin/check_in como equivalentes para validación
        # Si se permite checkin, también se permite check_in y viceversa
        normalized_allowed = set(allowed_transitions)
        if 'checkin' in normalized_allowed:
            normalized_allowed.add('check_in')
        if 'check_in' in normalized_allowed:
            normalized_allowed.add('checkin')
        
        if new_status not in normalized_allowed:
            raise ValueError(
                f'No se puede cambiar de estado "{current_status}" a "{new_status}". '
                f'Transiciones válidas: {", ".join(sorted(allowed_transitions)) if allowed_transitions else "ninguna"}'
            )

    def _validate_required_fields(self, data, required_fields):
        """Validar campos requeridos con mensaje específico"""
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            raise ValueError(
                f'Campos requeridos faltantes: {", ".join(missing_fields)}'
            )

    def _get_room_change_chain(self, booking):
        """
        Rastrea toda la cadena de cambios de habitación para una reserva.
        Retorna un diccionario con:
        - chain: lista de todas las reservas en la cadena (desde la original hasta la última)
        - original_booking: la reserva original (primera en la cadena)
        - current_position: posición de esta reserva en la cadena
        """
        # Verificar acceso a la reserva
        booking_checked = self._ensure_access(booking, 'read')
        chain = []
        visited = set()
        current = booking_checked
        
        # Rastrear hacia atrás para encontrar la reserva original
        while current and current.id not in visited:
            visited.add(current.id)
            chain.insert(0, current)  # Insertar al inicio para mantener orden cronológico
            
            # Buscar reserva anterior
            if hasattr(current, 'split_from_booking_id') and current.split_from_booking_id:
                current = self._ensure_access(current.split_from_booking_id, 'read')
            else:
                break
        
        # Rastrear hacia adelante desde la reserva original para encontrar todas las reservas siguientes
        if chain:
            original = chain[0]
            current = original
            
            # Buscar todas las reservas que tienen esta como split_from_booking_id
            while current:
                self._check_access_rights('hotel.booking', 'read')
                next_bookings = request.env['hotel.booking'].search([
                    ('split_from_booking_id', '=', current.id)
                ])
                self._check_access_rule(next_bookings, 'read')
                
                if next_bookings:
                    # Tomar la primera (debería haber solo una normalmente)
                    current = self._ensure_access(next_bookings[0], 'read')
                    if current.id not in visited:
                        visited.add(current.id)
                        chain.append(current)
                    else:
                        break
                else:
                    break
        
        # Encontrar la posición de la reserva actual en la cadena
        current_position = None
        for i, b in enumerate(chain):
            if b.id == booking.id:
                current_position = i
                break
        
        return {
            'chain': chain,
            'original_booking': chain[0] if chain else None,
            'current_position': current_position,
            'total_changes': len(chain) - 1 if len(chain) > 1 else 0,
        }
    
    def _build_room_info_from_booking(self, booking):
        """Construir información de habitaciones de una reserva"""
        booking_checked = self._ensure_access(booking, 'read')
        rooms = []
        if booking_checked and booking_checked.booking_line_ids:
            for line in booking_checked.booking_line_ids:
                if line.product_id:
                    rooms.append({
                        'id': line.product_id.id,
                        'name': line.product_id.name,
                        'code': line.product_id.default_code or '',
                        'template_id': line.product_id.product_tmpl_id.id if line.product_id.product_tmpl_id else None,
                    })
        return rooms
    
    def _build_booking_data(self, booking):
        """
        Construir datos de respuesta de reserva de forma optimizada
        
        Incluye información de cambio de habitación cuando aplica:
        - has_room_change: bool - Indica si la reserva tiene cambio de habitación
        - is_room_change_origin: bool - True si es la reserva original (primera en la cadena)
        - is_room_change_destination: bool - True si es una reserva con cambio (tiene reserva anterior)
        - connected_booking_id: int - ID de la reserva conectada inmediata
        - split_from_booking_id: int - ID de la reserva anterior inmediata
        - room_change_info: dict - Información resumida del cambio con habitaciones y posición en cadena
        - room_change_chain: array - Cadena completa de todas las reservas en la secuencia de cambios
        - connected_booking: dict - Datos de la reserva conectada inmediata con habitaciones (si existe)
        - original_booking: dict - Datos de la reserva anterior inmediata con habitaciones (si existe)
        
        Ejemplo de JSON con múltiples cambios de habitación:
        {
            "id": 125,
            "has_room_change": true,
            "is_room_change_origin": false,
            "is_room_change_destination": true,
            "connected_booking_id": 124,
            "split_from_booking_id": 124,
            "room_change_info": {
                "is_room_change": true,
                "is_origin": false,
                "is_destination": true,
                "connected_booking_id": 124,
                "split_from_booking_id": 124,
                "original_room": {
                    "id": 15,
                    "name": "Habitación 201",
                    "code": "ROOM-201",
                    "template_id": 8
                },
                "new_room": {
                    "id": 20,
                    "name": "Habitación 301",
                    "code": "ROOM-301",
                    "template_id": 12
                },
                "total_changes": 2,
                "current_position": 2,
                "chain_length": 3
            },
            "room_change_chain": [
                {
                    "booking_id": 123,
                    "sequence_id": "BOOK-001",
                    "check_in": "2024-01-15 14:00:00",
                    "check_out": "2024-01-20 11:00:00",
                    "status_bar": "checkin",
                    "position": 0,
                    "is_original": true,
                    "is_last": false,
                    "is_current": false,
                    "rooms": [
                        {
                            "id": 10,
                            "name": "Habitación 101",
                            "code": "ROOM-101",
                            "template_id": 5
                        }
                    ]
                },
                {
                    "booking_id": 124,
                    "sequence_id": "BOOK-002",
                    "check_in": "2024-01-20 14:00:00",
                    "check_out": "2024-01-25 11:00:00",
                    "status_bar": "checkin",
                    "position": 1,
                    "is_original": false,
                    "is_last": false,
                    "is_current": false,
                    "rooms": [
                        {
                            "id": 15,
                            "name": "Habitación 201",
                            "code": "ROOM-201",
                            "template_id": 8
                        }
                    ]
                },
                {
                    "booking_id": 125,
                    "sequence_id": "BOOK-003",
                    "check_in": "2024-01-25 14:00:00",
                    "check_out": "2024-01-30 11:00:00",
                    "status_bar": "checkin",
                    "position": 2,
                    "is_original": false,
                    "is_last": true,
                    "is_current": true,
                    "rooms": [
                        {
                            "id": 20,
                            "name": "Habitación 301",
                            "code": "ROOM-301",
                            "template_id": 12
                        }
                    ]
                }
            ],
            ...
        }
        """
        booking_checked = self._ensure_access(booking, 'read')
        # Calcular información de horas para reservas por horas
        check_in_hour = None
        check_in_minute = None
        check_out_hour = None
        check_out_minute = None
        is_half_day_checkin = False
        is_half_day_checkout = False
        
        if booking.check_in:
            try:
                check_in_dt = booking.check_in
                if isinstance(check_in_dt, datetime):
                    check_in_hour = check_in_dt.hour
                    check_in_minute = check_in_dt.minute
                    # Considerar medio día si el check-in es después de las 12:00 PM
                    is_half_day_checkin = check_in_hour >= 12
            except Exception:
                pass
        
        if booking.check_out:
            try:
                check_out_dt = booking.check_out
                if isinstance(check_out_dt, datetime):
                    check_out_hour = check_out_dt.hour
                    check_out_minute = check_out_dt.minute
                    # Considerar medio día si el check-out es antes de las 12:00 PM
                    is_half_day_checkout = check_out_hour < 12
            except Exception:
                pass
        
        booking_data = {
            'id': booking.id,
            'sequence_id': booking.sequence_id,
            'partner_id': booking.partner_id.id if booking.partner_id else None,
            'partner_name': booking.partner_id.name,
            'check_in': booking.check_in,
            'check_out': booking.check_out,
            'status_bar': booking.status_bar,
            # Información de horas para reservas por horas
            'check_in_hour': check_in_hour,
            'check_in_minute': check_in_minute,
            'check_out_hour': check_out_hour,
            'check_out_minute': check_out_minute,
            'is_half_day_checkin': is_half_day_checkin,
            'is_half_day_checkout': is_half_day_checkout,
            'hotel_id': booking.hotel_id.id if booking.hotel_id else None,
            'hotel_name': booking.hotel_id.name if booking.hotel_id else None,
            'motivo_viaje': booking.motivo_viaje or '',
            'responsible_name': booking.user_id.name if booking.user_id else None,
            'user_id': booking.user_id.id if booking.user_id else None,
            'description': booking.description or '',
            'booking_date': booking.booking_date,
            'create_date': booking.create_date,
            'write_date': booking.write_date,
            'booking_reference': booking.booking_reference,
            'origin': booking.origin or '',
            'pricelist_id': booking.pricelist_id.id if booking.pricelist_id else None,
            'pricelist_name': booking.pricelist_id.name if booking.pricelist_id else None,
            'currency_id': booking.currency_id.id if booking.currency_id else None,
            'currency_symbol': booking.currency_id.symbol if booking.currency_id else None,
            'amount_untaxed': booking.amount_untaxed,
            'total_amount': booking.total_amount,
            'booking_discount': booking.booking_discount,
            'tax_amount': booking.tax_amount,
            'booking_days': booking.booking_days,
            'cancellation_reason': booking.cancellation_reason or '',
            'via_agent': booking.via_agent,
            'agent_id': booking.agent_id.id if booking.agent_id else None,
            'agent_name': booking.agent_id.name if booking.agent_id else None,
            'commission_type': booking.commission_type or '',
            'agent_commission_amount': booking.agent_commission_amount,
            'agent_commission_percentage': booking.agent_commission_percentage,
            'company_id': booking.company_id.id if booking.company_id else None,
            'company_name': booking.company_id.name if booking.company_id else None,
        }
        
        # Información de órdenes de venta vinculadas a la reserva
        primary_order = booking.order_id
        if primary_order:
            booking_data.update({
                'order_id': primary_order.id,
                'order_name': primary_order.name,
                'order_state': primary_order.state,
                'order_amount_total': primary_order.amount_total,
                'order_currency_id': primary_order.currency_id.id if primary_order.currency_id else None,
                'order_currency_symbol': primary_order.currency_id.symbol if primary_order.currency_id else None,
            })
        else:
            booking_data.update({
                'order_id': None,
                'order_name': None,
                'order_state': None,
                'order_amount_total': 0.0,
                'order_currency_id': booking.currency_id.id if booking.currency_id else None,
                'order_currency_symbol': booking.currency_id.symbol if booking.currency_id else None,
            })
        
        # Verificar permisos antes de buscar órdenes de venta
        self._check_access_rights('sale.order', 'read')
        related_orders = request.env['sale.order'].search([
            ('booking_id', '=', booking.id)
        ])
        self._check_access_rule(related_orders, 'read')
        booking_data['sale_orders'] = [
            {
                'id': order.id,
                'name': order.name,
                'state': order.state,
                'amount_total': order.amount_total,
                'currency_id': order.currency_id.id if order.currency_id else None,
                'currency_symbol': order.currency_id.symbol if order.currency_id else None,
            }
            for order in related_orders
        ]
        
        # Campos de la extensión - usando un enfoque más limpio
        extension_fields = [
            'early_checkin_charge', 'late_checkout_charge', 'additional_charges_total',
            'discount_reason', 'manual_service_description', 'manual_service_amount'
        ]
        
        for field in extension_fields:
            if hasattr(booking, field):
                booking_data[field] = getattr(booking, field) or (0 if 'amount' in field or 'charge' in field else '')
        
        # Campos relacionales de la extensión
        if hasattr(booking, 'early_checkin_product_id') and booking.early_checkin_product_id:
            booking_data['early_checkin_product_id'] = booking.early_checkin_product_id.id
            booking_data['early_checkin_product_name'] = booking.early_checkin_product_id.name
        
        if hasattr(booking, 'late_checkout_product_id') and booking.late_checkout_product_id:
            booking_data['late_checkout_product_id'] = booking.late_checkout_product_id.id
            booking_data['late_checkout_product_name'] = booking.late_checkout_product_id.name
        
        # Información de cambio de habitación - Rastrear toda la cadena
        is_room_change_origin = False
        is_room_change_destination = False
        connected_booking_id = None
        split_from_booking_id = None
        
        # Obtener habitaciones de la reserva actual
        current_rooms = self._build_room_info_from_booking(booking_checked)
        
        # Rastrear toda la cadena de cambios
        change_chain = self._get_room_change_chain(booking_checked)
        chain = change_chain['chain']
        current_position = change_chain['current_position']
        total_changes = change_chain['total_changes']
        
        # Verificar si hay cambios
        if len(chain) > 1:
            booking_data['has_room_change'] = True
            
            # Determinar si es origen o destino
            if current_position == 0:
                is_room_change_origin = True
            elif current_position == len(chain) - 1:
                is_room_change_destination = True
            elif current_position is not None and current_position > 0:
                # Es un cambio intermedio
                is_room_change_destination = True  # Tiene una reserva anterior
            
            # Campos booleanos
            booking_data['is_room_change_origin'] = is_room_change_origin
            booking_data['is_room_change_destination'] = is_room_change_destination or (current_position is not None and current_position > 0)
            
            # Información de reservas conectadas (inmediatas)
            if hasattr(booking_checked, 'connected_booking_id') and booking_checked.connected_booking_id:
                connected_booking_id = booking_checked.connected_booking_id.id
                booking_data['connected_booking_id'] = connected_booking_id
                booking_data['connected_booking_sequence'] = booking_checked.connected_booking_id.sequence_id
                connected_booking = self._ensure_access(booking_checked.connected_booking_id, 'read')
                booking_data['connected_booking'] = {
                    'id': connected_booking.id,
                    'sequence_id': connected_booking.sequence_id,
                    'check_in': connected_booking.check_in,
                    'check_out': connected_booking.check_out,
                    'status_bar': connected_booking.status_bar,
                    'partner_name': connected_booking.partner_id.name if connected_booking.partner_id else None,
                    'rooms': self._build_room_info_from_booking(connected_booking),
                }
            
            if hasattr(booking_checked, 'split_from_booking_id') and booking_checked.split_from_booking_id:
                split_from_booking_id = booking_checked.split_from_booking_id.id
                booking_data['split_from_booking_id'] = split_from_booking_id
                booking_data['split_from_booking_sequence'] = booking_checked.split_from_booking_id.sequence_id
                original_booking_obj = self._ensure_access(booking_checked.split_from_booking_id, 'read')
                booking_data['original_booking'] = {
                    'id': original_booking_obj.id,
                    'sequence_id': original_booking_obj.sequence_id,
                    'check_in': original_booking_obj.check_in,
                    'check_out': original_booking_obj.check_out,
                    'status_bar': original_booking_obj.status_bar,
                    'partner_name': original_booking_obj.partner_id.name if original_booking_obj.partner_id else None,
                    'rooms': self._build_room_info_from_booking(original_booking_obj),
                }
            
            # Construir información completa de la cadena de cambios
            room_change_chain = []
            for i, chain_booking in enumerate(chain):
                chain_rooms = self._build_room_info_from_booking(chain_booking)
                room_change_chain.append({
                    'booking_id': chain_booking.id,
                    'sequence_id': chain_booking.sequence_id,
                    'check_in': chain_booking.check_in,
                    'check_out': chain_booking.check_out,
                    'status_bar': chain_booking.status_bar,
                    'position': i,
                    'is_original': i == 0,
                    'is_last': i == len(chain) - 1,
                    'is_current': chain_booking.id == booking.id,
                    'rooms': chain_rooms,
                })
            
            # Determinar habitaciones para el cambio actual
            original_room = None
            new_room = None
            
            if current_position is not None:
                if current_position > 0:
                    # Hay una reserva anterior
                    previous_booking = chain[current_position - 1]
                    prev_rooms = self._build_room_info_from_booking(previous_booking)
                    original_room = prev_rooms[0] if prev_rooms else None
                
                # Habitación nueva es la de esta reserva
                new_room = current_rooms[0] if current_rooms else None
                
                # Si hay siguiente reserva, también incluirla
                if current_position < len(chain) - 1:
                    next_booking = chain[current_position + 1]
                    next_rooms = self._build_room_info_from_booking(next_booking)
                    # La nueva habitación también puede ser la de la siguiente reserva
                    if not new_room and next_rooms:
                        new_room = next_rooms[0]
            
            # Información resumida de cambio de habitación
            booking_data['room_change_info'] = {
                'is_room_change': True,
                'is_origin': is_room_change_origin,
                'is_destination': is_room_change_destination or (current_position is not None and current_position > 0),
                'connected_booking_id': connected_booking_id,
                'split_from_booking_id': split_from_booking_id,
                'original_room': original_room,
                'new_room': new_room,
                'total_changes': total_changes,
                'current_position': current_position,
                'chain_length': len(chain),
            }
            
            # Agregar cadena completa de cambios
            booking_data['room_change_chain'] = room_change_chain
        else:
            # No hay cambios de habitación
            booking_data['has_room_change'] = False
            booking_data['is_room_change_origin'] = False
            booking_data['is_room_change_destination'] = False
            booking_data['room_change_info'] = {
                'is_room_change': False,
                'is_origin': False,
                'is_destination': False,
                'connected_booking_id': None,
                'split_from_booking_id': None,
                'original_room': None,
                'new_room': None,
                'total_changes': 0,
                'current_position': None,
                'chain_length': 1,
            }
            booking_data['room_change_chain'] = []
        
        # Agregar líneas de habitaciones y documentos
        booking_data['rooms'] = self._build_room_lines(booking.booking_line_ids)
        booking_data['documents'] = self._build_documents_data(booking.docs_ids)
        
        # Agregar lista de booking_sequence_id de las líneas (para las barras)
        booking_data['booking_line_sequence_ids'] = [
            line.booking_sequence_id 
            for line in booking.booking_line_ids 
            if line.booking_sequence_id
        ]
        
        # Determinar si se debe mostrar el botón de sincronizar servicios
        # El botón aparece solo si hay cambio de habitación o si es una reserva múltiple (múltiples habitaciones)
        has_room_change = booking_data.get('has_room_change', False)
        is_multiple_booking = len(booking.booking_line_ids) > 1
        booking_data['show_sync_services_button'] = has_room_change or is_multiple_booking
        
        return booking_data

    def _build_room_lines(self, booking_lines):
        """Construir datos de líneas de habitación optimizado"""
        room_lines = []
        
        for line in booking_lines:
            guest_list = [
                {
                    'id': guest.id,
                    'name': guest.name,
                    'age': guest.age,
                    'gender': guest.gender,
                    'is_adult': getattr(guest, 'is_adult', guest.age >= ADULT_AGE_THRESHOLD)
                }
                for guest in line.guest_info_ids
            ]
            
            line_data = {
                'id': line.id,
                'booking_sequence_id': line.booking_sequence_id,
                'product_id': line.product_id.id if line.product_id else None,
                'product_tmpl_id': line.product_tmpl_id.id if hasattr(line, 'product_tmpl_id') and line.product_tmpl_id else None,
                'room_name': line.product_id.name if line.product_id else None,
                'room_id': line.product_id.id if line.product_id else None,
                'room_code': getattr(line.product_id, 'default_code', None) if line.product_id else None,
                'room_barcode': getattr(line.product_id, 'barcode', None) if line.product_id else None,
                'guest_info': guest_list,
                'max_adult': getattr(line, 'max_adult', None),
                'max_child': getattr(line, 'max_child', None),
                'booking_days': line.booking_days,
                'price': line.price,
                'discount': getattr(line, 'discount', 0.0),
                'subtotal_price': getattr(line, 'subtotal_price', 0.0),
                'taxed_price': getattr(line, 'taxed_price', 0.0),
                'description': line.description or '',
                'status_bar': line.status_bar,
                'tax_ids': [tax.id for tax in line.tax_ids] if hasattr(line, 'tax_ids') else [],
                'currency_id': line.currency_id.id if hasattr(line, 'currency_id') and line.currency_id else None,
                'currency_symbol': line.currency_id.symbol if hasattr(line, 'currency_id') and line.currency_id else None,
            }
            
            # Campos de extensión
            for field in ['discount_amount', 'discount_reason', 'discount_percentage']:
                if hasattr(line, field):
                    line_data[field] = getattr(line, field) or (0.0 if 'amount' in field or 'percentage' in field else '')
            
            # Información de cambio de habitación en la línea
            if hasattr(line, 'is_room_change_segment'):
                line_data['is_room_change_segment'] = line.is_room_change_segment
            
            if hasattr(line, 'previous_line_id') and line.previous_line_id:
                line_data['previous_line_id'] = line.previous_line_id.id
                line_data['previous_line_sequence'] = getattr(line.previous_line_id, 'booking_sequence_id', None)
            
            if hasattr(line, 'next_line_id') and line.next_line_id:
                line_data['next_line_id'] = line.next_line_id.id
                line_data['next_line_sequence'] = getattr(line.next_line_id, 'booking_sequence_id', None)
            
            room_lines.append(line_data)
        
        return room_lines

    def _build_documents_data(self, docs_ids):
        """Construir datos de documentos adjuntos"""
        return [
            {
                'id': doc.id,
                'name': doc.name,
                'file_name': doc.file_name,
                'file_size': len(doc.file) if doc.file else 0,
                'has_file': bool(doc.file)
            }
            for doc in docs_ids
        ]

    def _create_booking_lines(self, booking_id, rooms_data):
        """Crear líneas de habitaciones con lógica mejorada"""
        booking = request.env['hotel.booking'].browse(booking_id)
        
        for room_data in rooms_data:
            product_id = room_data.get('product_id') or room_data.get('room_id')
            if not product_id:
                continue
            
            booking_line_vals = {
                'booking_id': booking_id,
                'product_id': product_id,
            }
            
            # Días de reserva
            if room_data.get('booking_days'):
                booking_line_vals['booking_days'] = room_data['booking_days']
            
            # Calcular precio
            if room_data.get('price'):
                booking_line_vals['price'] = float(room_data['price'])
            else:
                product = request.env['product.product'].browse(product_id)
                if booking.pricelist_id:
                    booking_line_vals['price'] = booking.pricelist_id._get_product_price(product, 1)
                else:
                    booking_line_vals['price'] = product.list_price
            
            # Descuento
            if room_data.get('discount') is not None:
                booking_line_vals['discount'] = float(room_data['discount'])
            
            # Impuestos
            if room_data.get('tax_ids'):
                tax_ids = room_data['tax_ids'] if isinstance(room_data['tax_ids'], list) else [room_data['tax_ids']]
                booking_line_vals['tax_ids'] = [(6, 0, tax_ids)]
            
            # Descripción
            if room_data.get('description'):
                booking_line_vals['description'] = room_data['description']
            
            # Crear línea de reserva
            booking_line = request.env['hotel.booking.line'].create(booking_line_vals)
            
            # Crear información de huéspedes
            if room_data.get('guests'):
                self._create_guest_info(booking_line.id, room_data['guests'])
            elif booking.partner_id:
                # Huésped por defecto: el partner principal
                default_guest = {
                    'partner_id': booking.partner_id.id,
                    'name': booking.partner_id.name,
                    'age': 30,
                    'gender': 'male'
                }
                self._create_guest_info(booking_line.id, [default_guest])

    def _create_guest_info(self, booking_line_id, guests_data):
        """Crear información de huéspedes con validación"""
        for guest_data in guests_data:
            # Obtener nombre del huésped
            if guest_data.get('partner_id'):
                partner = request.env['res.partner'].browse(guest_data['partner_id'])
                if not partner.exists():
                    raise ValueError(f'El partner con ID {guest_data["partner_id"]} no existe')
                guest_name = partner.name
            else:
                guest_name = guest_data.get('name', '')
            
            if not guest_name:
                raise ValueError('Debe especificar el nombre del huésped o un partner_id válido')
            
            guest_age = guest_data.get('age')
            if not guest_age:
                raise ValueError('Debe especificar la edad del huésped')
            
            guest_vals = {
                'booking_line_id': booking_line_id,
                'name': guest_name,
                'age': int(guest_age),
                'gender': guest_data.get('gender', 'male'),
            }
            
            # Agregar partner_id si existe
            if guest_data.get('partner_id'):
                guest_vals['partner_id'] = guest_data['partner_id']
            
            request.env['guest.info'].create(guest_vals)

    def _create_documents(self, booking_id, documents_data):
        """Crear documentos adjuntos para la reserva"""
        for doc_data in documents_data:
            if not doc_data.get('name'):
                continue
            
            doc_vals = {
                'booking_id': booking_id,
                'name': doc_data['name'],
                'file_name': doc_data.get('file_name', 'Document'),
            }
            
            if doc_data.get('file'):
                doc_vals['file'] = doc_data['file']
            
            request.env['hotel.document'].create(doc_vals)

    def _build_domain_from_filters(self, **filters):
        """Construir dominio de búsqueda desde filtros con validación"""
        domain = []
        
        # Filtro por hotel_id
        hotel_id_param = filters.get('hotel_id')
        if hotel_id_param is not None and hotel_id_param != '':
            try:
                hotel_id = self._validate_hotel_id(hotel_id_param)
                domain.append(('hotel_id', '=', hotel_id))
            except ValueError:
                raise
        
        # Filtro por partner_id
        if filters.get('partner_id'):
            partner_id = self._validate_partner_id(filters['partner_id'])
            domain.append(('partner_id', '=', partner_id))
        
        # Filtro por user_id
        if filters.get('user_id'):
            try:
                user_id = int(filters['user_id'])
                domain.append(('user_id', '=', user_id))
            except (ValueError, TypeError):
                raise ValueError('El user_id debe ser un número entero válido')
        
        # Filtro por estado
        if filters.get('status_bar'):
            status = filters['status_bar']
            self._validate_booking_status(status)
            domain.append(('status_bar', '=', status))
        
        return domain

    @http.route('/api/hotel/reservas/<int:hotel_id>', auth='public', type='http', methods=['GET'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def get_reservas_by_hotel_id(self, hotel_id, **kw):
        """
        Obtener reservas por ID de hotel
        
        Endpoint: GET /api/hotel/reservas/<hotel_id>
        
        Query Parameters:
            - partner_id: ID del huésped/cliente
            - user_id: ID del responsable/usuario
            - status_bar: Estado de la reserva
        """
        # Validar que el hotel existe
        self._check_access_rights('hotel.hotels', 'read')
        hotel = request.env['hotel.hotels'].browse(hotel_id)
        if not hotel.exists():
            return self._prepare_response({
                'success': False,
                'error': f'El hotel con ID {hotel_id} no existe'
            }, status=404)
        self._check_access_rule(hotel, 'read')
        
        # Construir dominio con hotel_id obligatorio
        filters = dict(kw, hotel_id=hotel_id)
        domain = self._build_domain_from_filters(**filters)
        
        # Verificar permisos antes de buscar reservas
        self._check_access_rights('hotel.booking', 'read')
        booking_records = request.env['hotel.booking'].search(domain)
        self._check_access_rule(booking_records, 'read')
        
        reservas_list = [self._build_booking_data(booking) for booking in booking_records]
        
        _logger.info(
            "Consulta exitosa: %s reservas recuperadas para hotel %s (%s)",
            len(reservas_list), hotel_id, hotel.name
        )
        
        return self._prepare_response({
            'success': True,
            'count': len(reservas_list),
            'hotel_id': hotel_id,
            'hotel_name': hotel.name,
            'data': reservas_list
        })

    @http.route('/api/hotel/reservas/habitacion/<int:room_id>', auth='public', type='http', methods=['GET'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def get_reservas_by_room_id(self, room_id, **kw):
        """
        Obtener reservas por ID de habitación
        
        Endpoint: GET /api/hotel/reservas/habitacion/<room_id>
        
        Query Parameters:
            - hotel_id: ID del hotel (opcional)
            - partner_id: ID del huésped/cliente
            - user_id: ID del responsable/usuario
            - status_bar: Estado de la reserva
        """
        # Validar que el producto existe
        self._check_access_rights('product.product', 'read')
        product = request.env['product.product'].browse(room_id)
        if not product.exists():
            return self._prepare_response({
                'success': False,
                'error': f'El producto con ID {room_id} no existe'
            }, status=404)
        self._check_access_rule(product, 'read')
        
        # Determinar si es tipo habitación y mensaje correspondiente
        is_room_type = product.is_room_type
        if is_room_type:
            room_type_message = "Es tipo de habitación"
        else:
            room_type_message = "No es tipo de habitación"
            _logger.warning(
                "Consulta de reservas por producto ID %s que no es tipo habitación: %s",
                room_id, product.name
            )
        
        # Buscar líneas de reserva que tengan esta habitación
        booking_lines_domain = [('product_id', '=', room_id)]
        
        # Si hay filtro por hotel_id, filtrar las reservas primero
        booking_ids_with_hotel = None
        if kw.get('hotel_id') or kw.get('hotel'):
            hotel_id_param = kw.get('hotel_id') or kw.get('hotel')
            try:
                hotel_id = self._validate_hotel_id(hotel_id_param)
                # Buscar las reservas que coincidan con el hotel_id
                self._check_access_rights('hotel.booking', 'read')
                booking_ids_with_hotel = request.env['hotel.booking'].search([
                    ('hotel_id', '=', hotel_id)
                ]).ids
                
                if booking_ids_with_hotel:
                    booking_lines_domain = booking_lines_domain + [('booking_id', 'in', booking_ids_with_hotel)]
                else:
                    # No hay reservas para este hotel, devolver conjunto vacío
                    return self._prepare_response({
                        'success': True,
                        'count': 0,
                        'room_id': room_id,
                        'room_name': product.name,
                        'is_room_type': is_room_type,
                        'room_type_message': room_type_message,
                        'data': []
                    })
            except ValueError:
                pass
        
        # Buscar líneas de reserva
        self._check_access_rights('hotel.booking.line', 'read')
        booking_lines = request.env['hotel.booking.line'].search(booking_lines_domain)
        
        # Obtener IDs de las reservas
        booking_ids_with_room = booking_lines.mapped('booking_id').ids
        
        if not booking_ids_with_room:
            return self._prepare_response({
                'success': True,
                'count': 0,
                'room_id': room_id,
                'room_name': product.name,
                'is_room_type': is_room_type,
                'room_type_message': room_type_message,
                'data': []
            })
        
        # Construir dominio con filtros adicionales (excluyendo hotel_id ya que se filtró antes)
        filters = {k: v for k, v in kw.items() if k not in ('hotel_id', 'hotel')}
        domain = self._build_domain_from_filters(**filters)
        
        # Agregar filtro de IDs de reservas que tienen esta habitación
        domain = domain + [('id', 'in', booking_ids_with_room)]
        
        # Verificar permisos antes de buscar reservas
        self._check_access_rights('hotel.booking', 'read')
        booking_records = request.env['hotel.booking'].search(domain)
        self._check_access_rule(booking_records, 'read')
        
        reservas_list = [self._build_booking_data(booking) for booking in booking_records]
        
        _logger.info(
            "Consulta exitosa: %s reservas recuperadas para habitación %s (%s)",
            len(reservas_list), room_id, product.name
        )
        
        return self._prepare_response({
            'success': True,
            'count': len(reservas_list),
            'room_id': room_id,
            'room_name': product.name,
            'room_code': product.default_code or '',
            'is_room_type': is_room_type,
            'room_type_message': room_type_message,
            'data': reservas_list
        })

    @http.route('/api/hotel/reservas', auth='public', type='http', methods=['GET'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def get_reservas(self, **kw):
        """
        Obtener todas las reservas con filtros opcionales
        
        Endpoint: GET /api/hotel/reservas
        
        Query Parameters:
            - partner_id: ID del huésped/cliente
            - hotel_id: ID del hotel (también acepta 'hotel' como alias)
            - user_id: ID del responsable/usuario
            - room_id: ID de la habitación (product_id)
            - product_id: ID de la habitación (alias de room_id)
            - status_bar: Estado de la reserva
        """
        # Limpiar parámetros vacíos o None
        cleaned_kw = {k: v for k, v in kw.items() if v not in (None, '', 'None')}
        
        # Normalizar parámetro hotel -> hotel_id (soporte para ambos nombres)
        if 'hotel' in cleaned_kw and 'hotel_id' not in cleaned_kw:
            cleaned_kw['hotel_id'] = cleaned_kw.pop('hotel')
        
        # Construir dominio desde filtros
        domain = self._build_domain_from_filters(**cleaned_kw)
        
        # VALIDACIÓN CRÍTICA: Si hay hotel_id en los parámetros, DEBE estar en el dominio
        hotel_id_param = cleaned_kw.get('hotel_id')
        if hotel_id_param:
            # Verificar que el dominio contiene el filtro de hotel_id
            has_hotel_filter = any(
                isinstance(term, tuple) and len(term) == 3 and term[0] == 'hotel_id' 
                for term in domain
            )
            
            if not has_hotel_filter:
                # Forzar agregar el filtro de hotel_id al dominio
                try:
                    hotel_id = self._validate_hotel_id(hotel_id_param)
                    domain.append(('hotel_id', '=', hotel_id))
                except Exception:
                    raise
        
        # Filtro por room_id/product_id (buscar en líneas de reserva)
        room_id_param = cleaned_kw.get('room_id') or cleaned_kw.get('product_id')
        room_type_info = None  # Para almacenar información del tipo de habitación
        if room_id_param:
            try:
                room_id = int(room_id_param)
                
                # Validar que el producto existe
                product = request.env['product.product'].browse(room_id)
                if not product.exists():
                    return self._prepare_response({
                        'success': False,
                        'error': f'El producto con ID {room_id} no existe'
                    }, status=404)
                
                # Determinar si es tipo habitación y mensaje correspondiente
                is_room_type = product.is_room_type
                if is_room_type:
                    room_type_message = "Es tipo de habitación"
                else:
                    room_type_message = "No es tipo de habitación"
                    _logger.warning(
                        "Consulta de reservas por producto ID %s que no es tipo habitación: %s",
                        room_id, product.name
                    )
                
                # Guardar información del tipo para incluir en la respuesta
                room_type_info = {
                    'room_id': room_id,
                    'room_name': product.name,
                    'is_room_type': is_room_type,
                    'room_type_message': room_type_message
                }
                
                # Si hay filtro por hotel_id, primero obtener las reservas del hotel
                booking_ids_with_hotel = None
                if cleaned_kw.get('hotel_id'):
                    hotel_id = self._validate_hotel_id(cleaned_kw['hotel_id'])
                    # Buscar las reservas que coincidan con el hotel_id
                    booking_ids_with_hotel = request.env['hotel.booking'].search([
                        ('hotel_id', '=', hotel_id)
                    ]).ids
                    
                    if not booking_ids_with_hotel:
                        # No hay reservas para este hotel, devolver conjunto vacío
                        response_data = {
                            'success': True,
                            'count': 0,
                            'data': []
                        }
                        # Agregar información del tipo de habitación si está disponible
                        if room_type_info:
                            response_data.update(room_type_info)
                        return self._prepare_response(response_data)
                
                # Buscar líneas de reserva que tengan esta habitación
                booking_lines_domain = [('product_id', '=', room_id)]
                
                # Si hay reservas del hotel, filtrar las líneas por esas reservas
                if booking_ids_with_hotel:
                    booking_lines_domain = booking_lines_domain + [('booking_id', 'in', booking_ids_with_hotel)]
                
                booking_lines = request.env['hotel.booking.line'].search(booking_lines_domain)
                
                # Obtener IDs de las reservas
                booking_ids_with_room = booking_lines.mapped('booking_id').ids
                
                if booking_ids_with_room:
                    # Aplicar el dominio completo incluyendo los filtros de hotel_id, partner_id, etc.
                    # Si el dominio está vacío, solo usar los IDs de reservas con esta habitación
                    if domain:
                        domain = domain + [('id', 'in', booking_ids_with_room)]
                    else:
                        domain = [('id', 'in', booking_ids_with_room)]
                else:
                    # No hay reservas con esta habitación, devolver conjunto vacío
                    response_data = {
                        'success': True,
                        'count': 0,
                        'data': []
                    }
                    # Agregar información del tipo de habitación si está disponible
                    if room_type_info:
                        response_data.update(room_type_info)
                    return self._prepare_response(response_data)
                    
            except (ValueError, TypeError):
                raise ValueError('El room_id/product_id debe ser un número entero válido')
        
        # Si hay filtros pero el dominio está vacío (y no se procesó room_id/product_id), forzar un dominio que no devuelva nada
        if not domain and cleaned_kw:
            # Excluir room_id y product_id de la verificación ya que se procesan antes
            other_filters = {k: v for k, v in cleaned_kw.items() if k not in ('room_id', 'product_id', 'hotel')}
            if other_filters:
                domain = [('id', '=', -1)]  # ID que no existe, devolverá conjunto vacío
        
        # Buscar reservas con el dominio completo (incluye todos los filtros)
        booking_records = request.env['hotel.booking'].sudo().search(domain)
        
        # Construir lista de respuestas
        reservas_list = [self._build_booking_data(booking) for booking in booking_records]
        
        _logger.info("Consulta exitosa: %s reservas recuperadas", len(reservas_list))
        
        # Preparar respuesta
        response_data = {
            'success': True,
            'count': len(reservas_list),
            'data': reservas_list
        }
        
        # Agregar información del hotel si se filtró por hotel_id
        hotel_id_value = cleaned_kw.get('hotel_id')
        if hotel_id_value:
            try:
                hotel_id = int(hotel_id_value)
                hotel = request.env['hotel.hotels'].browse(hotel_id)
                if hotel.exists():
                    response_data['hotel_id'] = hotel_id
                    response_data['hotel_name'] = hotel.name
            except (ValueError, TypeError):
                pass
        
        # Agregar información del tipo de habitación si se filtró por room_id/product_id
        if room_type_info:
            response_data.update(room_type_info)
        
        return self._prepare_response(response_data)

    @http.route('/api/hotel/reserva/<int:reserva_id>', auth='public', type='http', methods=['GET'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def get_reserva_by_id(self, reserva_id, **kw):
        """
        Obtener una reserva específica por ID
        
        Endpoint: GET /api/hotel/reserva/<reserva_id>
        """
        booking = request.env['hotel.booking'].browse(reserva_id)
        
        if not booking.exists():
            return self._prepare_response({
                'success': False,
                'error': f'La reserva con ID {reserva_id} no existe'
            }, status=404)
        
        # Verificar permisos de acceso
        self._check_access_rule(booking, 'read')
        
        return self._prepare_response({
            'success': True,
            'data': self._build_booking_data(booking)
        })

    @http.route('/api/hotel/reserva', auth='public', type='http', methods=['POST'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def create_reserva(self, **kw):
        """
        Crear una nueva reserva
        
        Endpoint: POST /api/hotel/reserva
        
        Body (JSON):
        {
            "partner_id": int (requerido),
            "user_id": int (requerido),
            "check_in": str (requerido, formato: YYYY-MM-DD HH:MM:SS),
            "check_out": str (requerido, formato: YYYY-MM-DD HH:MM:SS),
            "rooms": [ (requerido, al menos 1)
                {
                    "product_id": int o "room_id": int (requerido),
                    "price": float (opcional),
                    "discount": float (opcional, 0-100),
                    "guests": [ (opcional)
                        {
                            "name": str o "partner_id": int (requerido),
                            "age": int (requerido),
                            "gender": str (opcional: male, female, other)
                        }
                    ]
                }
            ],
            "hotel_id": int (opcional),
            "status_bar": str (opcional, default: initial),
            "motivo_viaje": str (opcional),
            "description": str (opcional),
            "via_agent": bool (opcional),
            "agent_id": int (opcional, requerido si via_agent=true),
            "commission_type": str (opcional: fixed, percentage),
            "documents": [ (opcional)
                {
                    "name": str (requerido),
                    "file_name": str (opcional),
                    "file": str (opcional, base64)
                }
            ]
        }
        """
        # Parsear datos JSON
        data = self._parse_json_data()
        
        # Validar campos requeridos
        required_fields = ['partner_id', 'check_in', 'check_out', 'rooms', 'user_id']
        self._validate_required_fields(data, required_fields)
        
        # Validaciones específicas
        check_in, check_out = self._validate_dates(data['check_in'], data['check_out'])
        self._validate_partner_id(data['partner_id'])
        self._validate_rooms_data(data['rooms'])
        
        # Normalizar estados: convertir variantes a 'checkin' para compatibilidad
        if data.get('status_bar') in ['checked_in', 'check_in']:
            original_status = data.get('status_bar')
            data['status_bar'] = 'checkin'
            _logger.info("Estado normalizado de '%s' a 'checkin' en creación", original_status)
        
        self._validate_booking_status(data.get('status_bar'))
        
        if data.get('hotel_id'):
            self._validate_hotel_id(data['hotel_id'])
        
        self._validate_booking_reference(data.get('booking_reference'))
        self._validate_agent_data(data)
        self._validate_documents_data(data.get('documents'))
        
        # Verificar permisos de creación
        self._check_access_rights('hotel.booking', 'create')
        self._check_access_rights('hotel.booking.line', 'create')
        booking_vals = {
            'partner_id': data['partner_id'],
            'user_id': data['user_id'],
            'check_in': check_in,
            'check_out': check_out,
            'status_bar': data.get('status_bar', 'initial'),
            'booking_date': datetime.now(),
        }
        
        # Campos opcionales básicos
        optional_fields = {
            'hotel_id': int,
            'product_tmpl_id': int,
            'pricelist_id': int,
            'origin': str,
            'booking_discount': float,
            'booking_reference': str,
            'description': str,
            'company_id': int,
            'cancellation_reason': str,
        }
        
        for field, field_type in optional_fields.items():
            if data.get(field) is not None:
                booking_vals[field] = field_type(data[field])
        
        # Fecha de reserva personalizada
        if data.get('booking_date'):
            try:
                booking_vals['booking_date'] = self._parse_datetime(data['booking_date'], 'booking_date')
            except ValueError:
                booking_vals['booking_date'] = datetime.now()
        
        # Campos de la extensión
        extension_fields = {
            'motivo_viaje': str,
            'early_checkin_charge': float,
            'late_checkout_charge': float,
            'early_checkin_product_id': int,
            'late_checkout_product_id': int,
            'discount_reason': str,
            'connected_booking_id': int,
            'split_from_booking_id': int,
            'manual_service_description': str,
            'manual_service_amount': float,
        }
        
        for field, field_type in extension_fields.items():
            if data.get(field) is not None:
                booking_vals[field] = field_type(data[field])
        
        # Datos de agente
        if data.get('via_agent'):
            booking_vals.update({
                'via_agent': True,
                'agent_id': data.get('agent_id'),
                'commission_type': data.get('commission_type', 'fixed'),
                'agent_commission_amount': float(data.get('agent_commission_amount', 0.0)),
                'agent_commission_percentage': float(data.get('agent_commission_percentage', 0.0)),
            })
        
        # Crear la reserva
        nueva_reserva = request.env['hotel.booking'].create(booking_vals)
        
        # Crear líneas de habitaciones y huéspedes
        self._create_booking_lines(nueva_reserva.id, data['rooms'])
        
        _logger.info(
            "Reserva %s (%s) creada exitosamente por usuario %s",
            nueva_reserva.id, nueva_reserva.sequence_id, request.env.user.name
        )
        
        return self._prepare_response({
            'success': True,
            'message': 'Reserva creada exitosamente',
            'data': {
                'reserva_id': nueva_reserva.id,
                'sequence_id': nueva_reserva.sequence_id,
                'partner_name': nueva_reserva.partner_id.name,
                'check_in': nueva_reserva.check_in,
                'check_out': nueva_reserva.check_out,
                'status_bar': nueva_reserva.status_bar,
                'total_amount': nueva_reserva.total_amount,
            }
        }, status=201)

    @http.route('/api/hotel/reserva/<int:reserva_id>', auth='public', type='http', methods=['PUT'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def update_reserva(self, reserva_id, **kw):
        """
        Actualizar una reserva existente
        
        Endpoint: PUT /api/hotel/reserva/<reserva_id>
        
        Body (JSON): Campos a actualizar (todos opcionales)
        """
        # Buscar reserva
        booking = request.env['hotel.booking'].browse(reserva_id)
        
        if not booking.exists():
            return self._prepare_response({
                'success': False,
                'error': f'La reserva con ID {reserva_id} no existe'
            }, status=404)
        
        # Verificar permisos de acceso y escritura
        self._check_access_rule(booking, 'read')
        self._check_access_rights('hotel.booking', 'write')
        self._check_access_rule(booking, 'write')
        
        # Parsear datos (JSON o form-data)
        data = self._parse_request_data()
        
        # Validar que la reserva se puede actualizar
        self._validate_booking_for_update(booking, data)
        
        # Preparar valores para actualización
        update_vals = {}
        
        # Actualizar fechas si se proporcionan
        if data.get('check_in') or data.get('check_out'):
            check_in_str = data.get('check_in', booking.check_in)
            check_out_str = data.get('check_out', booking.check_out)
            check_in, check_out = self._validate_dates(check_in_str, check_out_str)
            update_vals['check_in'] = check_in
            update_vals['check_out'] = check_out
        
        # Actualizar partner_id si se proporciona
        if data.get('partner_id'):
            partner_id = self._validate_partner_id(data['partner_id'])
            update_vals['partner_id'] = partner_id
        
        # Actualizar hotel_id si se proporciona
        if data.get('hotel_id'):
            hotel_id = self._validate_hotel_id(data['hotel_id'])
            update_vals['hotel_id'] = hotel_id
        
        # Actualizar estado si se proporciona
        new_status = data.get('status_bar')
        if new_status:
            # Normalizar estados: convertir variantes a 'checkin' para compatibilidad
            if new_status in ['checked_in', 'check_in']:
                original_status = new_status
                new_status = 'checkin'
                _logger.info("Estado normalizado de '%s' a 'checkin' en actualización", original_status)
            
            self._validate_status_transition(booking.status_bar, new_status)
            update_vals['status_bar'] = new_status
            
# Campos actualizables
        updatable_fields = [
            'user_id', 'motivo_viaje', 'description', 'booking_discount',
            'cancellation_reason', 'origin', 'pricelist_id', 'company_id',
            'early_checkin_charge', 'late_checkout_charge', 'discount_reason',
            'manual_service_description', 'manual_service_amount'
        ]
        
        for field in updatable_fields:
            if data.get(field) is not None:
                update_vals[field] = data[field]
        
        # Actualizar datos de agente
        if 'via_agent' in data:
            if data['via_agent']:
                self._validate_agent_data(data)
                update_vals.update({
                    'via_agent': True,
                    'agent_id': data.get('agent_id'),
                    'commission_type': data.get('commission_type'),
                    'agent_commission_amount': data.get('agent_commission_amount', 0.0),
                    'agent_commission_percentage': data.get('agent_commission_percentage', 0.0),
                })
            else:
                update_vals['via_agent'] = False
        
        # Aplicar actualización
        if update_vals:
            booking.write(update_vals)
            _logger.info(
                "Reserva %s actualizada exitosamente. Campos actualizados: %s",
                reserva_id, ', '.join(update_vals.keys())
            )
        
        return self._prepare_response({
            'success': True,
            'message': 'Reserva actualizada exitosamente',
            'data': self._build_booking_data(booking)
        })

    @http.route('/api/hotel/reserva/<int:reserva_id>', auth='public', type='http', methods=['DELETE'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def delete_reserva(self, reserva_id, **kw):
        """
        Eliminar (cancelar) una reserva
        
        Endpoint: DELETE /api/hotel/reserva/<reserva_id>
        
        Query Parameters:
            - force: bool (opcional) - Forzar eliminación física
        """
        booking = request.env['hotel.booking'].browse(reserva_id)
        
        if not booking.exists():
            return self._prepare_response({
                'success': False,
                'error': f'La reserva con ID {reserva_id} no existe'
            }, status=404)
        
        # Verificar permisos de acceso
        self._check_access_rule(booking, 'read')
        
        force_delete = kw.get('force', '').lower() in ['true', '1', 'yes']
        
        if force_delete:
            # Eliminación física - requiere permisos de eliminación
            self._check_access_rights('hotel.booking', 'unlink')
            self._check_access_rule(booking, 'unlink')
            sequence_id = booking.sequence_id
            booking.unlink()
            _logger.info("Reserva %s (%s) eliminada físicamente", reserva_id, sequence_id)
            
            return self._prepare_response({
                'success': True,
                'message': 'Reserva eliminada permanentemente',
                'reserva_id': reserva_id,
                'sequence_id': sequence_id
            })
        else:
            # Cancelación lógica - requiere permisos de escritura
            self._check_access_rights('hotel.booking', 'write')
            self._check_access_rule(booking, 'write')
            
            if booking.status_bar == 'cancelled':
                return self._prepare_response({
                    'success': False,
                    'error': 'La reserva ya está cancelada'
                }, status=400)
            
            booking.write({'status_bar': 'cancelled'})
            _logger.info("Reserva %s (%s) cancelada", reserva_id, booking.sequence_id)
            
            return self._prepare_response({
                'success': True,
                'message': 'Reserva cancelada exitosamente',
                'data': self._build_booking_data(booking)
            })

    @http.route('/api/hotel/reserva/<int:reserva_id>/habitaciones', auth='public', type='http', methods=['POST'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def add_rooms_to_reserva(self, reserva_id, **kw):
        """
        Agregar habitaciones a una reserva existente
        
        Endpoint: POST /api/hotel/reserva/<reserva_id>/habitaciones
        
        Body (JSON):
        {
            "rooms": [
                {
                    "product_id": int,
                    "guests": [...]
                }
            ]
        }
        """
        booking = request.env['hotel.booking'].browse(reserva_id)
        
        if not booking.exists():
            return self._prepare_response({
                'success': False,
                'error': f'La reserva con ID {reserva_id} no existe'
            }, status=404)
        
        # Verificar permisos
        self._check_access_rule(booking, 'read')
        self._check_access_rights('hotel.booking', 'write')
        self._check_access_rule(booking, 'write')
        self._check_access_rights('hotel.booking.line', 'create')
        
        # Validar que la reserva no esté en estado terminal
        if booking.status_bar in TERMINAL_STATUSES:
            return self._prepare_response({
                'success': False,
                'error': f'No se pueden agregar habitaciones a una reserva en estado "{booking.status_bar}"'
            }, status=400)
        
        data = self._parse_json_data()
        
        if not data.get('rooms'):
            raise ValueError('Debe especificar al menos una habitación')
        
        # Validar habitaciones
        self._validate_rooms_data(data['rooms'])
        
        # Crear líneas de habitaciones
        self._create_booking_lines(booking.id, data['rooms'])
        
        _logger.info(
            "Se agregaron %s habitaciones a la reserva %s",
            len(data['rooms']), reserva_id
        )
        
        return self._prepare_response({
            'success': True,
            'message': f'{len(data["rooms"])} habitación(es) agregada(s) exitosamente',
            'data': self._build_booking_data(booking)
        })


    @http.route('/api/hotel/reserva/<int:reserva_id>/estado', auth='public', type='http', methods=['PUT'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def change_reserva_status(self, reserva_id, **kw):
        """
        Cambiar el estado de una reserva
        
        Endpoint: PUT /api/hotel/reserva/<reserva_id>/estado
        
        Body (JSON):
        {
            "status_bar": str (requerido)
        }
        """
        booking = request.env['hotel.booking'].browse(reserva_id)
        
        if not booking.exists():
            return self._prepare_response({
                'success': False,
                'error': f'La reserva con ID {reserva_id} no existe'
            }, status=404)
        
        # Verificar permisos
        self._check_access_rule(booking, 'read')
        self._check_access_rights('hotel.booking', 'write')
        self._check_access_rule(booking, 'write')
        
        data = self._parse_request_data()
        _logger.info("=== CAMBIO DE ESTADO - Datos recibidos ===")
        _logger.info("Datos parseados: %s", {k: (v[:100] if isinstance(v, str) and len(v) > 100 else v) for k, v in data.items()})
        _logger.info("Estado actual de la reserva: %s", booking.status_bar)
        
        if not data.get('status_bar'):
            _logger.error("No se proporcionó status_bar en los datos")
            raise ValueError('Debe especificar el nuevo estado (status_bar)')
        
        new_status = data['status_bar']
        _logger.info("Nuevo estado solicitado: %s", new_status)
        
        # Normalizar estados: convertir variantes a 'checkin' para compatibilidad
        if new_status == 'checked_in' or new_status == 'check_in':
            new_status = 'checkin'
            _logger.info("Estado normalizado de '%s' a 'checkin'", data['status_bar'])
        
        # Validar estado
        self._validate_booking_status(new_status)
        
        # Validar transición
        self._validate_status_transition(booking.status_bar, new_status)
        
        # Actualizar estado
        old_status = booking.status_bar
        final_status = new_status
        triggered_action = False
        
        if new_status in ['confirmed', 'confirm'] and hasattr(booking, 'action_confirm_booking'):
            _logger.info("Ejecutando action_confirm_booking para la reserva %s", reserva_id)
            try:
                booking.action_confirm_booking()
                triggered_action = True
                # Después de la acción tomamos el estado real desde el registro
                final_status = booking.status_bar
            except Exception as exc:
                _logger.error("Error ejecutando action_confirm_booking en reserva %s: %s", reserva_id, str(exc), exc_info=True)
                raise ValueError(f'No se pudo confirmar la reserva: {str(exc)}')
        else:
            booking.write({'status_bar': new_status})
        
        _logger.info(
            "Estado de reserva %s cambiado de '%s' a '%s'%s",
            reserva_id,
            old_status,
            final_status,
            ' mediante action_confirm_booking' if triggered_action else ''
        )
        
        response_data = {
            'reserva_id': reserva_id,
            'old_status': old_status,
            'new_status': final_status,
            'sequence_id': booking.sequence_id
        }
        
        message = f'Estado cambiado de "{old_status}" a "{final_status}"'
        
        return self._prepare_response({
            'success': True,
            'message': message,
            'data': response_data
        })
    
    @http.route('/api/hotel/reserva/<int:reserva_id>/send_email', auth='public', type='http', methods=['POST'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def send_reserva_email(self, reserva_id, **kw):
        """
        Enviar correo relacionado a la reserva

        Endpoint: POST /api/hotel/reserva/<reserva_id>/send_email

        Body (JSON) opcional:
        {
            "template_xml_id": "hotel_management_system.hotel_booking_confirm_id",
            "force_send": true,
            "email_values": { ... }   # Valores extra para mail.compose.message
        }
        """
        booking = request.env['hotel.booking'].browse(reserva_id)

        if not booking.exists():
            return self._prepare_response({
                'success': False,
                'error': f'La reserva con ID {reserva_id} no existe'
            }, status=404)

        # Verificar permisos
        self._check_access_rule(booking, 'read')
        try:
            request.env['mail.template'].check_access_rights('read', raise_exception=True)
        except AccessError:
            return self._prepare_response({
                'success': False,
                'error': 'No tiene permisos para enviar correos'
            }, status=403)

        data = self._parse_json_data()
        template_xml_id = data.get('template_xml_id', 'hotel_management_system.hotel_booking_confirm_id')
        force_send = bool(data.get('force_send', True))
        email_values = data.get('email_values') or {}

        template = request.env.ref(template_xml_id, raise_if_not_found=False)
        if not template:
            raise ValueError(f'No se encontró la plantilla de correo "{template_xml_id}".')

        mail_template = request.env['mail.template'].browse(template.id)

        try:
            mail_template.send_mail(
                booking.id,
                force_send=force_send,
                email_values=email_values if isinstance(email_values, dict) else {}
            )
        except Exception as exc:
            _logger.error("Error enviando correo para la reserva %s: %s", reserva_id, str(exc), exc_info=True)
            raise ValueError(f'No se pudo enviar el correo: {str(exc)}')

        return self._prepare_response({
            'success': True,
            'message': 'Correo enviado correctamente',
            'data': {
                'reserva_id': booking.id,
                'template_xml_id': template_xml_id
            }
        })

    @http.route('/api/hotel/reserva/<int:reserva_id>/advance_payment', auth='public', type='http', methods=['POST'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def create_reserva_advance_payment(self, reserva_id, **kw):
        """
        Generar un anticipo (down payment) para la orden de venta ligada a la reserva.

        Endpoint: POST /api/hotel/reserva/<reserva_id>/advance_payment

        Body (JSON):
        {
            "advance_payment_method": "percentage" | "fixed" | "delivered",
            "amount": 30.0,                # requerido para percentage/fixed (en porcentaje o monto fijo)
            "product_id": 123,             # opcional, producto de anticipo
            "consolidated_billing": true,  # opcional
            "deduct_down_payments": true   # opcional para delivered
        }
        """
        booking = request.env['hotel.booking'].browse(reserva_id)

        if not booking.exists():
            return self._prepare_response({
                'success': False,
                'error': f'La reserva con ID {reserva_id} no existe'
            }, status=404)

        # Verificar permisos
        self._check_access_rule(booking, 'read')
        self._check_access_rights('sale.order', 'read')
        self._check_access_rights('account.move', 'create')

        if not booking.order_id:
            raise ValueError('La reserva no tiene una orden de venta asociada. Confirme la reserva primero.')
        
        self._check_access_rule(booking.order_id, 'read')

        data = self._parse_json_data()
        method = data.get('advance_payment_method', 'percentage')

        if method not in ['percentage', 'fixed', 'delivered']:
            raise ValueError('advance_payment_method debe ser "percentage", "fixed" o "delivered".')

        wizard_vals = {
            'advance_payment_method': method,
        }

        if method == 'percentage':
            if data.get('amount') is None:
                raise ValueError('Debe especificar "amount" (porcentaje) para el anticipo.')
            wizard_vals['amount'] = float(data['amount'])
        elif method == 'fixed':
            if data.get('amount') is None:
                raise ValueError('Debe especificar "amount" (monto fijo) para el anticipo.')
            wizard_vals['fixed_amount'] = float(data['amount'])
        else:  # delivered
            wizard_vals['deduct_down_payments'] = bool(data.get('deduct_down_payments', True))

        if data.get('product_id'):
            wizard_vals['product_id'] = int(data['product_id'])

        if data.get('consolidated_billing') is not None:
            wizard_vals['consolidated_billing'] = bool(data['consolidated_billing'])

        if data.get('deposit_account_id'):
            wizard_vals['deposit_account_id'] = int(data['deposit_account_id'])

        if data.get('deposit_taxes_id'):
            wizard_vals['deposit_taxes_id'] = [(6, 0, [int(t) for t in data['deposit_taxes_id']])]

        ctx = {
            'active_model': 'sale.order',
            'active_id': booking.order_id.id,
            'active_ids': booking.order_id.ids,
            'default_sale_order_ids': booking.order_id.ids,
        }

        wizard_env = request.env['sale.advance.payment.inv'].with_context(ctx)
        wizard = wizard_env.create(wizard_vals)

        existing_invoice_ids = set(booking.order_id.invoice_ids.ids)
        wizard.create_invoices()
        booking.order_id.invalidate_recordset(['invoice_ids'])
        invoices = booking.order_id.invoice_ids.filtered(lambda inv: inv.id not in existing_invoice_ids)

        invoice_payload = [
            {
                'id': invoice.id,
                'name': invoice.name,
                'amount_total': invoice.amount_total,
                'currency_id': invoice.currency_id.id,
                'state': invoice.state,
            }
            for invoice in invoices
        ]

        return self._prepare_response({
            'success': True,
            'message': 'Anticipo creado exitosamente',
            'data': {
                'reserva_id': booking.id,
                'sale_order_id': booking.order_id.id,
                'advance_payment_method': method,
                'invoices_created': invoice_payload,
            }
        })

    @http.route('/api/hotel/reserva/<int:reserva_id>/advance_payment/options', auth='public', type='http', methods=['GET'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def get_reserva_advance_payment_options(self, reserva_id, **kw):
        """
        Obtener valores predeterminados y opciones del wizard de anticipo.

        Endpoint: GET /api/hotel/reserva/<reserva_id>/advance_payment/options
        """
        booking = request.env['hotel.booking'].browse(reserva_id)

        if not booking.exists():
            return self._prepare_response({
                'success': False,
                'error': f'La reserva con ID {reserva_id} no existe'
            }, status=404)

        if not booking.order_id:
            raise ValueError('La reserva no tiene una orden de venta asociada. Confirme la reserva primero.')

        ctx = {
            'active_model': 'sale.order',
            'active_id': booking.order_id.id,
            'active_ids': booking.order_id.ids,
            'default_sale_order_ids': booking.order_id.ids,
        }

        wizard_env = request.env['sale.advance.payment.inv'].with_context(ctx)
        wizard_record = wizard_env.new({})

        def _record_to_dict(record, fields_map):
            values = {}
            for key, getter in fields_map.items():
                values[key] = getter(record)
            return values

        defaults = _record_to_dict(wizard_record, {
            'advance_payment_method': lambda r: r.advance_payment_method,
            'amount': lambda r: r.amount,
            'fixed_amount': lambda r: r.fixed_amount,
            'has_down_payments': lambda r: bool(r.has_down_payments),
            'deduct_down_payments': lambda r: bool(r.deduct_down_payments),
            'consolidated_billing': lambda r: bool(r.consolidated_billing),
            'amount_invoiced': lambda r: r.amount_invoiced,
            'amount_to_invoice': lambda r: r.amount_to_invoice,
            'product_id': lambda r: r.product_id.id if r.product_id else None,
            'product_name': lambda r: r.product_id.display_name if r.product_id else None,
            'currency': lambda r: {
                'id': booking.order_id.currency_id.id,
                'name': booking.order_id.currency_id.name,
                'symbol': booking.order_id.currency_id.symbol,
            },
            'customer': lambda r: booking.order_id.partner_id.display_name,
            'date': lambda r: fields.Date.context_today(request.env.user),
        })

        selection_field = wizard_record._fields['advance_payment_method']
        selection_values = selection_field.selection
        if callable(selection_values):
            selection_values = selection_values(wizard_env.env)
        selection_options = [{'value': value, 'label': label} for value, label in selection_values]

        response_payload = {
            'defaults': defaults,
            'advance_payment_methods': selection_options,
        }

        return self._prepare_response({
            'success': True,
            'data': response_payload
        })

    @http.route('/api/hotel/hoteles', auth='public', type='http', methods=['GET'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def get_hoteles(self, **kw):
        """
        Obtener lista de hoteles disponibles
        
        Endpoint: GET /api/hotel/hoteles
        """
        hotels = request.env['hotel.hotels'].search([])
        
        hotels_list = [
            {
                'id': hotel.id,
                'name': hotel.name,
                'active': hotel.active if hasattr(hotel, 'active') else True,
            }
            for hotel in hotels
        ]
        
        return self._prepare_response({
            'success': True,
            'count': len(hotels_list),
            'data': hotels_list
        })

    @http.route('/api/hotel/habitaciones', auth='public', type='http', methods=['GET'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def get_habitaciones(self, **kw):
        """
        Obtener lista de habitaciones (productos tipo habitación)
        
        Endpoint: GET /api/hotel/habitaciones
        
        Query Parameters:
            - hotel_id: int (opcional) - Filtrar por hotel
        """
        domain = [('is_room_type', '=', True)]
        
        if kw.get('hotel_id'):
            hotel_id = self._validate_hotel_id(kw['hotel_id'])
            # Agregar filtro por hotel si el campo existe en el modelo
            # domain.append(('hotel_id', '=', hotel_id))
        
        products = request.env['product.product'].search(domain)
        
        rooms_list = [
            {
                'id': product.id,
                'name': product.name,
                'code': product.default_code or '',
                'barcode': product.barcode or '',
                'list_price': product.list_price,
                'active': product.active,
            }
            for product in products
        ]
        
        return self._prepare_response({
            'success': True,
            'count': len(rooms_list),
            'data': rooms_list
        })

    @http.route(
        '/api/hotel/reserva/<int:reserva_id>/update_guests',
        auth='public',
        type='http',
        methods=['POST', 'PUT'],
        csrf=False,
        website=False
    )
    @validate_api_key
    def update_guests(self, reserva_id, **kw):
        """
        Agregar o actualizar huéspedes en una reserva existente
        
        Endpoint: POST/PUT /api/hotel/reserva/<reserva_id>/update_guests
        
        Body JSON:
        {
            "booking_line_id": int (opcional, si no se proporciona se agregan a todas las líneas),
            "guests": [
                {
                    "name": str (requerido si no hay partner_id),
                    "partner_id": int (opcional),
                    "age": int (requerido),
                    "gender": str (opcional, default: "male")
                },
                ...
            ],
            "replace": bool (opcional, default: false - si true, reemplaza todos los huéspedes existentes)
        }
        """
        try:
            booking = self._ensure_access(
                request.env['hotel.booking'].browse(reserva_id),
                'write'
            )
            
            if not booking.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'La reserva con ID {reserva_id} no existe'
                }, status=404)
            
            # Verificar que la reserva pueda ser modificada
            terminal_states = ['cancelled', 'no_show', 'checkout']
            if booking.status_bar in terminal_states:
                return self._prepare_response({
                    'success': False,
                    'error': f'No se puede modificar una reserva en estado "{booking.status_bar}"'
                }, status=400)
            
            # Obtener datos del request
            try:
                data = self._parse_json_data()
            except ValueError as e:
                return self._prepare_response({
                    'success': False,
                    'error': str(e)
                }, status=400)
            
            if not data:
                return self._prepare_response({
                    'success': False,
                    'error': 'Debe proporcionar datos en formato JSON'
                }, status=400)
            
            guests_data = data.get('guests', [])
            if not guests_data:
                return self._prepare_response({
                    'success': False,
                    'error': 'Debe proporcionar al menos un huésped'
                }, status=400)
            
            booking_line_id = data.get('booking_line_id')
            replace = data.get('replace', False)
            
            # Determinar a qué líneas agregar los huéspedes
            if booking_line_id:
                booking_line = request.env['hotel.booking.line'].browse(booking_line_id)
                if not booking_line.exists() or booking_line.booking_id.id != reserva_id:
                    return self._prepare_response({
                        'success': False,
                        'error': f'La línea de reserva con ID {booking_line_id} no existe o no pertenece a esta reserva'
                    }, status=404)
                booking_lines = booking_line
            else:
                # Agregar a todas las líneas de la reserva
                booking_lines = booking.booking_line_ids
            
            if not booking_lines:
                return self._prepare_response({
                    'success': False,
                    'error': 'La reserva no tiene líneas de habitación'
                }, status=400)
            
            # Validar datos de huéspedes considerando los existentes si replace = False
            for booking_line in booking_lines:
                # Si replace = False, incluir huéspedes existentes en la validación
                if not replace and booking_line.guest_info_ids:
                    # Combinar huéspedes existentes con los nuevos para validación
                    existing_guests = []
                    for existing_guest in booking_line.guest_info_ids:
                        existing_guests.append({
                            'name': existing_guest.name,
                            'age': existing_guest.age,
                            'gender': existing_guest.gender,
                            'partner_id': existing_guest.partner_id.id if existing_guest.partner_id else None
                        })
                    # Validar todos los huéspedes (existentes + nuevos)
                    all_guests = existing_guests + guests_data
                else:
                    # Si replace = True, solo validar los nuevos
                    all_guests = guests_data
                
                try:
                    self._validate_guests_data(all_guests, booking_line.id)
                except ValueError as e:
                    return self._prepare_response({
                        'success': False,
                        'error': str(e)
                    }, status=400)
            
            guests_added = 0
            
            for booking_line in booking_lines:
                # Si replace es true, eliminar huéspedes existentes
                if replace:
                    booking_line.guest_info_ids.unlink()
                
                # Agregar nuevos huéspedes
                try:
                    self._create_guest_info(booking_line.id, guests_data)
                    guests_added += len(guests_data)
                except ValueError as e:
                    return self._prepare_response({
                        'success': False,
                        'error': str(e)
                    }, status=400)
            
            # Obtener información actualizada de la reserva
            booking_data = self._build_booking_data(booking)
            
            _logger.info(
                'Huéspedes actualizados en reserva %s: %d agregados',
                reserva_id,
                guests_added
            )
            
            return self._prepare_response({
                'success': True,
                'message': f'Se agregaron {guests_added} huésped(es) a la reserva',
                'data': {
                    'reserva_id': reserva_id,
                    'guests_added': guests_added,
                    'booking': booking_data
                }
            }, status=200)
            
        except ValueError as e:
            _logger.warning('Error de validación en update_guests: %s', str(e))
            return self._prepare_response({
                'success': False,
                'error': str(e)
            }, status=400)
        except (AccessError, MissingError) as e:
            _logger.warning('Error de acceso en update_guests: %s', str(e))
            return self._prepare_response({
                'success': False,
                'error': 'No tiene permisos para modificar esta reserva'
            }, status=403)
        except Exception as e:
            _logger.exception('Error inesperado en update_guests: %s', str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/health', auth='public', type='http', methods=['GET'], csrf=False, website=False)
    def health_check(self, **kw):
        """
        Verificar estado del API
        
        Endpoint: GET /api/hotel/health
        """
        return self._prepare_response({
            'success': True,
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0'
        })

    @http.route('/api/hotel/gantt/data', auth='public', type='http', methods=['GET'], csrf=False, website=False)
    @validate_api_key
    @handle_api_errors
    def get_gantt_data(self, **kw):
        """
        Obtener datos del Gantt con información completa de horas para reservas (optimizado para React)
        
        Endpoint: GET /api/hotel/gantt/data
        
        Parámetros de consulta:
        - target_date: str (opcional, formato: YYYY-MM-DD, default: hoy)
        - hotel_id: int (opcional, filtrar por hotel)
        - start_date: str (opcional, formato: YYYY-MM-DD, para rango personalizado)
        - end_date: str (opcional, formato: YYYY-MM-DD, para rango personalizado)
        
        Respuesta JSON estructurada:
        {
            "success": true,
            "data": {
                "rooms": [...],  // Lista de habitaciones
                "reservations": [...],  // Lista de reservas con información completa de horas
                "month_info": {...},  // Información del mes
                "metadata": {...}  // Metadatos adicionales
            }
        }
        
        Cada reserva incluye:
        - date_start: ISO datetime string (YYYY-MM-DDTHH:MM:SS)
        - date_end: ISO datetime string (YYYY-MM-DDTHH:MM:SS)
        - check_in_hour: int (0-23)
        - check_in_minute: int (0-59)
        - check_out_hour: int (0-23)
        - check_out_minute: int (0-59)
        - is_half_day_checkin: bool
        - is_half_day_checkout: bool
        - duration_hours: float (duración total en horas)
        - duration_days: float (duración total en días)
        """
        try:
            # Obtener parámetros
            target_date_str = kw.get('target_date')
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date() if target_date_str else datetime.now().date()
            
            hotel_id = kw.get('hotel_id')
            if hotel_id:
                try:
                    hotel_id = int(hotel_id)
                except (ValueError, TypeError):
                    hotel_id = None
            
            # Obtener habitaciones
            domain = [('is_room_type', '=', True)]
            if hotel_id:
                domain.append(('hotel_id', '=', hotel_id))
            
            rooms = request.env['product.template'].sudo().search_read(
                domain,
                fields=['id', 'name', 'list_price', 'max_adult', 'max_child', 'hotel_id'],
                order='name',
                limit=1000
            )
            
            # Procesar habitaciones
            for room in rooms:
                room['room_type_id'] = False
                max_adult = room.get('max_adult', 1)
                max_child = room.get('max_child', 0)
                room['capacity'] = max_adult + max_child
                room['price'] = room.get('list_price', 0.0)
                
                # Procesar hotel_id
                original_hotel_id = room.get('hotel_id')
                if original_hotel_id:
                    if isinstance(original_hotel_id, (list, tuple)) and len(original_hotel_id) >= 2:
                        room['hotel_id'] = list(original_hotel_id) if isinstance(original_hotel_id, tuple) else original_hotel_id
                    elif isinstance(original_hotel_id, (int, str)):
                        try:
                            hotel_id_int = int(original_hotel_id)
                            hotel = request.env['hotel.hotels'].sudo().browse(hotel_id_int)
                            if hotel.exists():
                                room['hotel_id'] = [hotel_id_int, hotel.name]
                            else:
                                room['hotel_id'] = False
                        except (ValueError, TypeError):
                            room['hotel_id'] = False
                    else:
                        room['hotel_id'] = False
                else:
                    room['hotel_id'] = False
            
            # Obtener reservas del mes
            first_day = target_date.replace(day=1)
            last_day = first_day + timedelta(days=31)
            
            domain = [
                ('check_in', '<=', datetime.combine(last_day, datetime.max.time())),
                ('check_out', '>=', datetime.combine(first_day, datetime.min.time())),
                ('status_bar', 'not in', ['cancel', 'cancelled', 'room_ready']),
            ]
            
            bookings = request.env['hotel.booking'].sudo().search_read(
                domain,
                fields=['id', 'check_in', 'check_out', 'status_bar', 'partner_id', 'total_amount', 'currency_id', 
                       'connected_booking_id', 'is_room_change_origin', 'is_room_change_destination'],
                limit=1000
            )
            
            booking_ids = [b['id'] for b in bookings]
            booking_lines = request.env['hotel.booking.line'].sudo().search_read(
                [('booking_id', 'in', booking_ids)],
                fields=['id', 'booking_id', 'product_tmpl_id', 'booking_days', 'discount_reason']
            )
            
            lines_by_booking = {}
            for line in booking_lines:
                if line.get('booking_id'):
                    booking_id = line['booking_id'][0]
                    if booking_id not in lines_by_booking:
                        lines_by_booking[booking_id] = []
                    lines_by_booking[booking_id].append(line)
            
            # Construir reservas con información de horas
            reservations = []
            for booking in bookings:
                booking_id = booking.get('id')
                if booking_id and booking_id in lines_by_booking:
                    booking_check_in = booking.get('check_in')
                    booking_check_out = booking.get('check_out')
                    
                    if not booking_check_in or not booking_check_out:
                        continue
                    
                    # Convertir a timezone local
                    try:
                        check_in_base = fields.Datetime.context_timestamp(request.env.user, booking_check_in)
                        check_out_base = fields.Datetime.context_timestamp(request.env.user, booking_check_out)
                    except:
                        check_in_base = booking_check_in
                        check_out_base = booking_check_out
                    
                    # Calcular información completa de horas y minutos de la reserva principal
                    booking_check_in_hour = None
                    booking_check_in_minute = None
                    booking_check_out_hour = None
                    booking_check_out_minute = None
                    booking_duration_hours = None
                    booking_duration_days = None
                    
                    if isinstance(check_in_base, datetime):
                        booking_check_in_hour = check_in_base.hour
                        booking_check_in_minute = check_in_base.minute
                    
                    if isinstance(check_out_base, datetime):
                        booking_check_out_hour = check_out_base.hour
                        booking_check_out_minute = check_out_base.minute
                        
                        # Calcular duración total de la reserva principal
                        if isinstance(check_in_base, datetime):
                            duration_delta = check_out_base - check_in_base
                            booking_duration_hours = duration_delta.total_seconds() / 3600.0
                            booking_duration_days = duration_delta.days + (duration_delta.seconds / 86400.0)
                    
                    lines = sorted(lines_by_booking[booking_id], key=lambda x: x.get('id', 0))
                    current_date = check_in_base
                    
                    # Detectar cambios de habitación
                    has_room_changes = len(lines) > 1 and any(
                        line.get('product_tmpl_id') != lines[0].get('product_tmpl_id') 
                        for line in lines[1:] 
                        if line.get('product_tmpl_id')
                    )
                    
                    for i, line in enumerate(lines):
                        if line.get('product_tmpl_id'):
                            booking_days = line.get('booking_days', 0)
                            if booking_days <= 0:
                                continue
                            
                            if has_room_changes:
                                if i == 0:
                                    line_start = check_in_base
                                    # Usar booking_days directamente (puede ser fraccional para reservas de pocas horas)
                                    line_end = check_in_base + timedelta(days=booking_days)
                                else:
                                    # Calcular fecha de inicio basándose en la fecha de cambio
                                    change_start = check_in_base + timedelta(days=sum(lines[j].get('booking_days', 0) for j in range(i)))
                                    line_start = change_start
                                    # Usar booking_days directamente (puede ser fraccional)
                                    line_end = change_start + timedelta(days=booking_days)
                            else:
                                line_start = current_date
                                # Usar booking_days directamente (puede ser fraccional para reservas de pocas horas)
                                line_end = current_date + timedelta(days=booking_days)
                                current_date = line_end
                            
                            # Obtener precio y moneda
                            total_amount = booking.get('total_amount', 0.0)
                            currency_symbol = ''
                            if booking.get('currency_id') and isinstance(booking['currency_id'], (list, tuple)) and len(booking['currency_id']) > 1:
                                currency_symbol = booking['currency_id'][1]
                            elif booking.get('currency_id') and isinstance(booking['currency_id'], (list, tuple)) and len(booking['currency_id']) > 0:
                                try:
                                    currency = request.env['res.currency'].sudo().browse(booking['currency_id'][0])
                                    if currency.exists():
                                        currency_symbol = currency.symbol
                                except:
                                    currency_symbol = '$'
                            else:
                                currency_symbol = '$'
                            
                            # Calcular información de horas para esta línea específica
                            line_check_in_hour = None
                            line_check_in_minute = None
                            line_check_out_hour = None
                            line_check_out_minute = None
                            line_is_half_day_checkin = False
                            line_is_half_day_checkout = False
                            line_duration_hours = None
                            line_duration_days = None
                            
                            if isinstance(line_start, datetime):
                                line_check_in_hour = line_start.hour
                                line_check_in_minute = line_start.minute
                                line_is_half_day_checkin = line_check_in_hour >= 12
                            
                            if isinstance(line_end, datetime):
                                line_check_out_hour = line_end.hour
                                line_check_out_minute = line_end.minute
                                line_is_half_day_checkout = line_check_out_hour < 12
                                
                                # Calcular duración de esta línea específica
                                if isinstance(line_start, datetime):
                                    line_duration_delta = line_end - line_start
                                    line_duration_hours = line_duration_delta.total_seconds() / 3600.0
                                    line_duration_days = line_duration_delta.days + (line_duration_delta.seconds / 86400.0)
                            
                            reservation_data = {
                                'id': line.get('id', 0),
                                'booking_id': booking_id or 0,
                                'date_start': line_start.isoformat() if hasattr(line_start, 'isoformat') else str(line_start),
                                'date_end': line_end.isoformat() if hasattr(line_end, 'isoformat') else str(line_end),
                                'state': booking.get('status_bar', ''),
                                'status_bar': booking.get('status_bar', ''),
                                'customer_name': booking['partner_id'][1] if booking.get('partner_id') and booking['partner_id'] and len(booking['partner_id']) > 1 else 'N/A',
                                'partner_id': booking['partner_id'][0] if booking.get('partner_id') and booking['partner_id'] and len(booking['partner_id']) > 0 else None,
                                'room_id': [line['product_tmpl_id'][0], line['product_tmpl_id'][1]] if line.get('product_tmpl_id') and line['product_tmpl_id'] and len(line['product_tmpl_id']) > 1 else [0, ''],
                                'room_name': line['product_tmpl_id'][1] if line.get('product_tmpl_id') and line['product_tmpl_id'] and len(line['product_tmpl_id']) > 1 else '',
                                'total_amount': total_amount,
                                'currency_symbol': currency_symbol,
                                'discount_reason': line.get('discount_reason', '') or '',
                                # Información completa de horas para reservas por horas
                                'check_in_hour': line_check_in_hour,
                                'check_in_minute': line_check_in_minute,
                                'check_out_hour': line_check_out_hour,
                                'check_out_minute': line_check_out_minute,
                                'is_half_day_checkin': line_is_half_day_checkin,
                                'is_half_day_checkout': line_is_half_day_checkout,
                                'duration_hours': round(line_duration_hours, 2) if line_duration_hours is not None else None,
                                'duration_days': round(line_duration_days, 2) if line_duration_days is not None else None,
                                # Información de la reserva principal (para referencia)
                                'booking_check_in': booking_check_in.isoformat() if isinstance(booking_check_in, datetime) else str(booking_check_in),
                                'booking_check_out': booking_check_out.isoformat() if isinstance(booking_check_out, datetime) else str(booking_check_out),
                                'booking_check_in_hour': booking_check_in_hour,
                                'booking_check_in_minute': booking_check_in_minute,
                                'booking_check_out_hour': booking_check_out_hour,
                                'booking_check_out_minute': booking_check_out_minute,
                                'booking_duration_hours': round(booking_duration_hours, 2) if booking_duration_hours is not None else None,
                                'booking_duration_days': round(booking_duration_days, 2) if booking_duration_days is not None else None,
                            }
                            
                            if has_room_changes:
                                reservation_data['is_room_change'] = True
                            else:
                                reservation_data['is_new_reservation'] = True
                            
                            if booking.get('connected_booking_id'):
                                reservation_data['connected_booking_id'] = booking['connected_booking_id'][0] if isinstance(booking['connected_booking_id'], (list, tuple)) else booking['connected_booking_id']
                                reservation_data['is_room_change_origin'] = booking.get('is_room_change_origin', False)
                                reservation_data['is_room_change_destination'] = booking.get('is_room_change_destination', False)
                            
                            reservations.append(reservation_data)
            
            # Construir información del mes
            if target_date.month == 12:
                last_day_month = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                last_day_month = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)
            
            days = list(range(1, last_day_month.day + 1))
            
            month_info = {
                'month_name': target_date.strftime('%B %Y').title(),
                'month_number': target_date.month,
                'year': target_date.year,
                'days': days,
                'first_day': first_day.isoformat(),
                'last_day': last_day_month.isoformat(),
                'total_days': len(days),
            }
            
            # Metadatos adicionales útiles para React
            metadata = {
                'total_rooms': len(rooms),
                'total_reservations': len(reservations),
                'hotel_id': hotel_id,
                'target_date': target_date.isoformat(),
                'generated_at': datetime.now().isoformat(),
                'timezone': str(request.env.user.tz) if request.env.user.tz else 'UTC',
            }
            
            return self._prepare_response({
                'success': True,
                'data': {
                    'rooms': rooms,
                    'reservations': reservations,
                    'month_info': month_info,
                    'metadata': metadata
                }
            })
            
        except Exception as e:
            _logger.exception("Error obteniendo datos del Gantt: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': str(e)
            }, status=500)