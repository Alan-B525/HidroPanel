# Plan de implementación: API ONS para Hidrología de Yacyretá

**Fecha:** 15 de octubre de 2026  
**Objetivo:** evolucionar el sitio hacia un visor operacional de datos ONS, sin calcular previsiones propias ni presentar como medido un “aporte a Yacyretá”.

## 1. Decisión de arquitectura

La decisión propuesta es pasar a un enfoque **API-first para los datos recientes**, manteniendo el Parquet únicamente como herramienta auxiliar:

- La API será la fuente principal del sitio para datos actuales.
- El Parquet no será requisito para que el sitio funcione.
- Los archivos mensuales podrán descargarse manualmente desde ONS cuando se necesite análisis histórico o auditoría.
- La aplicación no calculará previsiones propias.
- Las previsiones se mostrarán solamente cuando estén disponibles en la API y se etiquetarán con su organismo/origen, fecha de emisión y fecha de validez.
- No se mostrará un KPI llamado “aporte a Yacyretá” mientras no exista una medición directa o una metodología hidrológica validada.

Esto simplifica la operación diaria y elimina la dependencia de mantener archivos locales actualizados. A cambio, el sitio debe manejar correctamente token, caídas de servicio, datos faltantes, calidad, latencia y límites de consulta.

## 2. Alcance funcional

### 2.1 Datos actuales prioritarios

Para Itaipú, Baixo Iguaçu y los reservatorios que se definan con Hidrología:

1. Afluencia (`AFL`).
2. Defluencia (`DFL`).
3. Caudal turbinado (`TUR`).
4. Caudal vertido (`VER`).
5. Caudal de otras estructuras (`VOE`), si está disponible.
6. Nivel montante (`NIV`/endpoint de nivel).
7. Nivel jusante.
8. Volumen útil.
9. Timestamp de medición.
10. Origen y calidad del dato.

### 2.2 Información adicional de alto valor

- Precipitación observada horaria y diaria.
- Previsiones diarias publicadas por ONS u otros organismos disponibles en la API.
- Indicador de energía turbinable.
- Caudal natural e incremental para análisis contextual.
- Estado de actualización, antigüedad y calidad de cada serie.

### 2.3 Elementos que deben eliminarse o reformularse

- El KPI “aporte a Yacyretá” debe retirarse del resumen principal.
- La suma de defluencias de Itaipú y Baixo Iguaçu no debe presentarse como caudal de Yacyretá.
- Cualquier valor calculado debe llamarse explícitamente “indicador derivado” y mostrar su fórmula, timestamp y limitaciones.
- El sitio debe diferenciar:
  - **Dato observado/verificado:** devuelto por la API.
  - **Previsión externa:** publicada por un organismo y devuelta por la API.
  - **Indicador derivado:** cálculo local, si en el futuro se autoriza.

## 3. Arquitectura técnica objetivo

```text
ONS API
  ├─ autenticación y renovación
  ├─ catálogo de reservatorios
  ├─ grandezas actuales
  ├─ precipitación
  └─ previsiones externas
          |
          v
Backend HidroPanel
  ├─ cliente ONS
  ├─ caché temporal
  ├─ normalización y validación
  ├─ estado de fuente/calidad
  └─ adaptador de salida para FWEB/FWES
          |
          +--> API JSON del sitio actual
          +--> exportación o integración futura con FWEB/FWES
          |
          v
Frontend
  ├─ tablero operacional
  ├─ series y tablas
  ├─ previsiones externas etiquetadas
  └─ estado/antigüedad de datos
```

La API ONS debe consumirse desde el backend, nunca directamente desde el navegador. Así se protegen las credenciales, se centralizan los reintentos y se evita que cada usuario genere llamadas independientes a ONS.

## 4. Fases de trabajo

### Fase 0 — Definición operativa y acceso

**Resultado:** acceso probado y catálogo validado.

- Confirmar autorización de `IntegracaoHidrologia` en SINTEGRE.
- Crear credenciales de servicio separadas de usuarios personales.
- Confirmar expiración de `access_token` y funcionamiento de `refresh_token`.
- Consultar `/hidrologia/reservatorios`.
- Identificar los `Identificador` reales de Itaipú, Baixo Iguaçu y demás puntos de interés.
- Confirmar zona horaria, unidades y significado de cada variable con el área de Hidrología.
- Confirmar qué previsiones y organismos son devueltos por el endpoint de previsiones.

**Entregable:** matriz `codigo_local -> Identificador ONS -> nombre -> cuenca -> variables habilitadas`.

### Fase 1 — Cliente backend ONS

**Resultado:** un cliente aislado, testeable y reutilizable.

Implementar un módulo específico, por ejemplo `backend/services/ons_api_client.py`, con:

- `authenticate()`
- `renew_token()`
- `list_reservoirs()`
- `get_verified_measurement(reservoir_id, variable, start, end, interval, origin)`
- `get_hydrological_measurements(reservoir_ids, variable, start, end, quality, aggregation)`
- `get_precipitation(...)`
- `get_forecast(reservoir_id, start, valid_dates, page)`

El cliente debe:

- Usar timeout explícito.
- Validar códigos HTTP y estructura JSON.
- Manejar token vencido con una sola renovación y reintento.
- Aplicar reintentos limitados únicamente a errores transitorios.
- Registrar latencia, endpoint, rango consultado y cantidad de resultados.
- No registrar contraseñas, tokens ni respuestas completas con datos sensibles.
- Exponer errores diferenciados: autenticación, permisos, límite, timeout, respuesta inválida y servicio no disponible.

### Fase 2 — Normalización y caché

**Resultado:** una respuesta uniforme para el frontend y futuras integraciones.

Normalizar todas las respuestas a una estructura como:

```json
{
  "reservatorio_id": "PNITAI",
  "timestamp": "2026-10-15T14:00:00-03:00",
  "variable": "defluencia",
  "valor": 12345.6,
  "unidad": "m3/s",
  "intervalo": "HO",
  "origem": "TRL",
  "qualidade": "CON",
  "fonte": "ONS_API",
  "consultado_em": "2026-10-15T15:20:00-03:00"
}
```

La caché puede ser inicialmente en memoria o SQLite, con estas reglas:

- Datos recientes: refresco cada 10-15 minutos, según la política acordada.
- Catálogo: refresco diario o bajo demanda.
- Precipitación: frecuencia independiente de los caudales.
- Previsiones: refresco al cambiar fecha de emisión/validación o cada 1-3 horas.
- Nunca reemplazar un dato reciente válido por una respuesta vacía.
- Marcar la hora del último dato exitoso y la hora del último intento.

La caché no debe convertirse en un histórico obligatorio. Su objetivo es reducir latencia, evitar llamadas duplicadas y mantener la última lectura válida durante una interrupción breve.

### Fase 3 — Cambios de backend del sitio

**Resultado:** el sitio consume API ONS sin cambiar la interfaz pública del frontend más de lo necesario.

Adaptar `backend/services/represas_service.py` para que:

1. Obtenga los datos recientes mediante el cliente ONS.
2. Mantenga una función de normalización común para API y cualquier fallback.
3. Deje de depender de `fetch_ons_file_for_month()` para las consultas operativas.
4. Conserve la descarga Parquet como comando opcional de respaldo/manual.
5. No calcule `q_total_yacyreta` como si fuera una medición.
6. Entregue al frontend valores y metadatos de fuente:

```json
{
  "success": true,
  "fuente": "ONS_API",
  "actualizado_en": "...",
  "antiguedad_segundos": 320,
  "estado": "actual",
  "itaipu": {
    "afluente": {},
    "defluente": {},
    "turbinada": {},
    "vertida": {},
    "nivel_montante": {},
    "nivel_jusante": {},
    "volume_util": {}
  }
}
```

El backend debe devolver estado explícito cuando no pueda actualizar:

- `actual`: lectura dentro del umbral.
- `demorado`: última lectura válida, pero supera el umbral operativo.
- `sin_datos`: no existe lectura utilizable.
- `error_autenticacion`: requiere intervención.
- `error_ons`: ONS no disponible o respondió con error.

### Fase 4 — Rediseño del panel

**Resultado:** el usuario ve datos operativos y su contexto, sin inferencias engañosas.

#### Tablero de reservatorios

Para cada reservatorio:

- Afluencia.
- Defluencia.
- Turbinado.
- Vertido.
- Nivel montante.
- Nivel jusante.
- Volumen útil.
- Hora del dato.
- Origen/calidad.
- Estado de actualización.

#### Gráficos

- Serie horaria de las últimas 24-72 horas.
- Selector de variable.
- Selector de reservatorio.
- Comparación entre dato preliminar y consolidado cuando ambos existan.
- Línea o etiqueta de previsión externa separada de la observación.
- Tooltip con unidad, timestamp, origen y calidad.

#### Previsiones externas

Crear una sección separada, no mezclada con datos observados:

- Organismo/origen.
- Fecha de emisión.
- Fecha de inicio.
- Fecha de validez.
- Valor previsto.
- Tipo de previsión.
- Indicador de previsión oficial, si la API lo informa.

#### Precipitación

- Acumulado horario/diario.
- Estación meteorológica.
- Calidad y existencia de huecos.
- Relación visual con cambios de afluencia, sin afirmar causalidad automática.

### Fase 5 — Pruebas paralelas y aceptación

Durante 7-14 días:

- Consultar API y Parquet en paralelo, sin usar todavía el resultado API para alertas.
- Comparar variables equivalentes por reservatorio y timestamp.
- Medir latencia, errores, datos faltantes y cambios retroactivos.
- Validar unidades y zona horaria.
- Simular token vencido.
- Simular timeout y respuesta HTTP 500.
- Simular respuesta vacía.
- Desconectar la API y verificar que el panel muestra estado demorado, no datos inventados.

## 5. Diseño pensando en FWEB/FWES

Como todavía no se dispone del acceso al sistema destino, la integración debe desacoplarse desde el inicio.

### 5.1 Contrato interno estable

El backend debe producir un modelo canónico independiente de ONS. FWEB/FWES no debería recibir directamente la respuesta cruda de ONS, porque la API puede cambiar nombres, paginación o formatos.

Contrato mínimo recomendado:

```text
source_system
source_record_id
station_or_reservoir_id
timestamp_measurement
timestamp_received
variable_code
value
unit
aggregation
quality
origin
status
```

### 5.2 Adaptador de salida

Crear posteriormente un módulo separado, por ejemplo:

```text
backend/integrations/fwes_adapter.py
```

El adaptador deberá transformar el modelo canónico al formato requerido por FWEB/FWES, sin alterar el cliente ONS ni el frontend.

### 5.3 Modos de integración posibles

Dejar preparados tres modos, a decidir cuando exista acceso:

1. **Push:** el backend envía registros nuevos al sistema destino.
2. **Pull:** FWEB/FWES consulta un endpoint del backend.
3. **Archivo/cola:** el backend genera archivos o mensajes en el formato acordado.

Antes de implementar la salida se deberá confirmar:

- Protocolo y URL.
- Autenticación.
- Formato y esquema.
- Frecuencia esperada.
- Política de reintentos.
- Identificador idempotente.
- Confirmación de recepción.
- Correcciones y reprocesamiento.
- Requisitos de auditoría.

## 6. Modelo de datos mínimo recomendado

Aunque no se quiera mantener un histórico local completo, conviene conservar una caché operativa y trazabilidad:

### `ons_reservoirs`

- `ons_id`
- `codigo_local`
- `nombre`
- `bacia`
- `activo`
- `updated_at`

### `ons_observations`

- `id`
- `reservoir_id`
- `timestamp`
- `variable`
- `value`
- `unit`
- `interval`
- `origin`
- `quality`
- `source`
- `received_at`
- `raw_hash`

### `ons_forecasts`

- `reservoir_id`
- `variable`
- `forecast_value`
- `forecast_start`
- `valid_date`
- `issued_at`
- `origin`
- `official`
- `received_at`

### `ons_sync_runs`

- `started_at`
- `finished_at`
- `status`
- `endpoint`
- `records_received`
- `http_status`
- `error_code`
- `latency_ms`

La retención de estas tablas puede limitarse a la ventana operativa definida por el equipo. Los archivos mensuales seguirán disponibles en ONS para análisis históricos.

## 7. Indicadores que sí conviene mostrar

- Última afluencia por reservatorio.
- Última defluencia por reservatorio.
- Diferencia turbinado vs. defluente.
- Vertimiento actual y acumulado del período consultado.
- Nivel montante y jusante.
- Volumen útil.
- Tiempo desde la última actualización.
- Origen y calidad del dato.
- Precipitación observada.
- Previsión externa, claramente separada.
- Estado de conectividad con ONS.

## 8. Indicadores que no conviene mostrar inicialmente

- “Aporte a Yacyretá” como suma directa de otros reservatorios.
- Caudal futuro calculado por el sitio.
- Alertas hidrológicas basadas en umbrales no validados.
- Promedios que mezclen `TRL`, `CON`, `COO` y `ATR` sin identificarlos.
- Series que mezclen horarios locales y UTC sin conversión explícita.

## 9. Criterios de aceptación

La primera versión API-first se considerará lista cuando:

- El sitio pueda actualizar datos sin descargar Parquet.
- El token no aparezca en frontend, logs ni archivos versionados.
- Cada dato muestre timestamp, unidad, origen y calidad disponibles.
- Una caída de ONS produzca estado `demorado` o `sin_datos`, nunca un valor presentado como actual.
- Las previsiones aparezcan en una vista diferenciada y con organismo/origen.
- El frontend no muestre el antiguo KPI de aporte a Yacyretá.
- El cliente soporte renovación de token, timeout, respuesta vacía y errores HTTP.
- Exista un endpoint backend estable para futuras integraciones.
- El modelo canónico pueda transformarse a un formato externo sin modificar la adquisición ONS.

## 10. Orden recomendado de implementación

1. Confirmar identificadores y acceso API.
2. Implementar cliente autenticado y pruebas de contrato.
3. Implementar catálogo y mapeo de reservatorios.
4. Implementar observaciones de AFL/DFL/TUR/VER.
5. Implementar caché, estado de actualización y errores explícitos.
6. Reemplazar la fuente operativa del backend.
7. Retirar el KPI de aporte a Yacyretá.
8. Actualizar tablero, tablas y gráficos.
9. Incorporar niveles, volumen útil y precipitación.
10. Incorporar previsiones externas.
11. Ejecutar piloto paralelo API-Parquet.
12. Definir y construir el adaptador FWEB/FWES cuando se tenga acceso al sistema destino.

## Conclusión

La propuesta del usuario es técnicamente razonable: para un sitio dedicado a **consultar datos actuales**, la API es más cómoda que depender de archivos mensuales locales. El cambio debe hacerse como una migración API-first, no como una simple sustitución de URL. La prioridad es que el backend controle autenticación, caché, calidad, errores y normalización; el frontend debe mostrar datos observados y previsiones externas de forma inequívoca; y la futura conexión con FWEB/FWES debe consumir un contrato interno estable.
