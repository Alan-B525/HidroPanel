# Evaluación de la API ONS para el sector Hidrología de Yacyretá

**Fecha de evaluación:** 15 de octubre de 2026  
**Fuente evaluada:** `api_ons.txt` (especificación OpenAPI disponible en el proyecto)  
**Fuente actualmente integrada:** dataset mensual ONS en S3, preferentemente Parquet

## 1. Resumen ejecutivo

La API ONS debe ser la fuente principal del monitoreo operativo del sitio. El Parquet puede conservarse como recurso opcional para análisis históricos y auditoría, pero no debe ser una dependencia de la consulta diaria.

**Recomendación:** implementar una arquitectura API-first con caché operativa:

1. **API ONS:** fuente principal para datos recientes, consulta bajo demanda, metadatos, precipitación, previsiones externas y grandezas verificadas.
2. **Caché/base local limitada:** última lectura válida, estado de actualización, trazabilidad y preparación para FWEB/FWES.
3. **Parquet ONS:** recurso opcional para históricos y auditoría, accesible desde ONS cuando sea necesario.

La API mejora la frescura potencial y amplía la información disponible, especialmente con `AFL`, `DFL`, `TUR`, `VER`, niveles, volumen útil, precipitaciones y previsiones externas. La ventana máxima de **7 días** no es un impedimento para un visor operacional, aunque sí limita los análisis históricos. La dependencia de autenticación y disponibilidad debe resolverse con caché, estados explícitos de antigüedad, renovación de token y manejo de errores.

## 2. Alcance y evidencia revisada

Se revisaron:

- La especificación OpenAPI de la API ONS en `api_ons.txt`.
- La integración actual en `backend/services/represas_service.py`.
- El cliente y las rutas de sincronización del panel.
- El archivo local `data/DADOS_HIDROLOGICOS_HO_2026_10.parquet`.

La evaluación de la API es documental. No se realizó una llamada autenticada porque las credenciales no están incluidas en el repositorio. Antes de adoptar la API en producción debe ejecutarse una prueba controlada con credenciales de servicio y con los identificadores reales de Itaipú, Baixo Iguaçu y demás puntos relevantes.

## 3. Situación actual: Parquet

La implementación vigente descarga el dataset mensual de datos abiertos ONS desde S3:

`https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/dados_hidrologicos_ho/DADOS_HIDROLOGICOS_HO_YYYY_MM.parquet`

Características observadas en el código:

- Prioriza Parquet y usa CSV como fallback.
- Comprueba el archivo remoto con `HEAD` y vuelve a descargar si cambia su tamaño.
- Lee únicamente las columnas necesarias mediante PyArrow y filtra por `id_reservatorio`.
- Mantiene hasta 72 registros por presa para las curvas del panel.
- La sincronización programada actual se ejecuta cada 30 minutos; el resumen mantiene una caché en memoria de 10 minutos.
- El resumen combina el defluente de Itaipú con el defluente de Baixo Iguaçu para estimar el aporte hacia Yacyretá.

### Medición del archivo local

El Parquet local disponible al momento de la evaluación contiene:

| Elemento | Resultado |
|---|---:|
| Registros totales | 59.156 |
| Reservatorios distintos | 170 |
| Cobertura temporal | 2026-10-01 01:00 a 2026-10-15 14:00 |
| Registros de PNITAI | 350 |
| Registros de IGUHBI | 350 |
| Variables numéricas principales | nivel montante, nivel jusante, volumen útil, afluencia, defluencia, turbinada, vertida |
| Variables adicionales presentes | otras estructuras, transferida, vertida no turbinable |

Para los reservatorios principales, 350 registros equivalen aproximadamente a una serie horaria de los primeros 14 días y parte del día 15. El archivo mensual permite conservar una serie más amplia que la ventana máxima documentada para las consultas operativas de la API.

## 4. Qué aporta la API para Yacyretá

### 4.1 Grandezas directamente relevantes

La API documenta tanto endpoints específicos por reservatorio como una consulta general de grandezas. Las métricas más relevantes son:

| Código/API | Concepto | Uso para Yacyretá |
|---|---|---|
| `AFL` / `afluencia` | Afluencia al reservatorio | Seguimiento del aporte que llegará a la cadena aguas abajo y detección de cambios hidrológicos |
| `DFL` / `defluencia` | Descarga o defluencia total | Variable principal para estimar el caudal que sale de Itaipú y llega al sistema Paraná-Yacyretá |
| `TUR` / `vazaoTurbinada` | Caudal turbinado | Separar generación hidráulica de descarga total |
| `VER` / `vazaoVertida` | Caudal vertido | Detectar vertimiento, restricciones de generación y eventos operativos |
| `NIV` / `nivelMontante` | Nivel del reservatorio | Estado hidráulico del embalse |
| `nivelJusante` | Nivel aguas abajo | Relación nivel-caudal, control operacional y consistencia |
| `volumeUtil` | Volumen útil | Contexto de almacenamiento y capacidad de regulación |
| `VTR` / `energiaTurbinavel` | Indicador de energía turbinable | Indicador energético complementario para operación |
| `VOE` | Caudal de otras estructuras | Completar el balance cuando no todo el caudal se explica por turbinas y vertedero |
| `VIA` | Caudal incremental agrupado | Análisis del aporte entre reservatorios |
| `VNA`, `VNM`, `VNS` | Caudales naturales e incrementales modelados | Pronóstico, atribución hidrológica y análisis de tendencia |

La especificación también expone:

- **Precipitación observada**, con agregación horaria o diaria y estados de calidad.
- **Previsiones de caudal diario por reservatorio**, incluyendo origen, período, tipo de previsión y si es oficial.
- **Catálogo de reservatorios**, útil para validar identificadores y nombres.

### 4.2 Calidad y procedencia

La API permite seleccionar origen para endpoints específicos:

- `TRL`: tiempo real.
- `SSC`: tiempo real leído del sistema de supervisión.
- `FTP`: tiempo real leído del servidor FTP.
- `ATR`: valor atribuido.

En la consulta general se documentan calidades `COO` (consolidado) y `CON` (consistido), además de agregación `HO` (horaria) o `DI` (diaria). Esto es una ventaja frente a tratar todos los valores del Parquet como equivalentes: el panel puede distinguir dato operativo, dato consolidado, dato atribuido y dato faltante.

## 5. Comparación API frente a Parquet

| Criterio | API ONS | Parquet ONS actual | Evaluación |
|---|---|---|---|
| Frescura operativa | Potencialmente mejor; ofrece orígenes de tiempo real | Depende de la publicación mensual y actualización del archivo | Ventaja API |
| Histórico largo | No documentado; endpoints específicos limitan a 7 días | Naturalmente adecuado por archivos mensuales | Ventaja Parquet |
| Afluencia, defluencia, turbinada y vertida | Sí, con endpoints específicos y consulta general | Sí, ya presentes en las columnas locales | Empate en cobertura básica |
| Niveles y volumen útil | Sí | Sí | Empate |
| Precipitación observada | Sí | No es el foco del dataset hidrológico actual | Ventaja API |
| Previsiones | Sí, previsión diaria | No | Ventaja API |
| Reproducibilidad | Requiere guardar respuestas y parámetros | Alta si se conserva el archivo original | Ventaja Parquet |
| Dependencia de credenciales | Sí; requiere autorización SINTEGRE | No para el dataset público S3 | Ventaja Parquet |
| Dependencia de disponibilidad | Servicio autenticado y red en cada consulta | Puede operar con copia local | Ventaja Parquet |
| Paginación/ventana de consulta | Máximo documentado de 7 días y 240 elementos por página en endpoints específicos | Sin límite funcional equivalente; lectura local | Ventaja Parquet |
| Latencia para el panel | Red, token y consulta remota | Lectura local/caché | Ventaja Parquet |
| Detección de correcciones | Debe implementarse comparación y upsert | Se puede conservar cada archivo descargado | Depende del diseño |
| Ampliación futura | Más indicadores y previsiones sin cambiar el origen | Requiere nuevos datasets/procesadores | Ventaja API |

## 6. Implicaciones específicas para el balance de Yacyretá

El cálculo actualmente implementado es una aproximación:

`Q_total_Yacyretá ≈ Q_defluente_Itaipú + Q_defluente_Baixo_Iguaçu`

Es útil para operación, pero debe mostrarse como **estimación de aporte** y no como caudal medido en Yacyretá. La API no elimina por sí sola las siguientes consideraciones:

1. **Tiempo de tránsito:** la defluencia de Itaipú y Baixo Iguaçu no ocurre en el mismo instante en Yacyretá. Debe documentarse y, si se usa para alerta o pronóstico, calibrarse un desfase.
2. **Aportes intermedios:** existen afluentes y aportes entre los puntos de control. `VIA`, estaciones fluviométricas, precipitación y datos de otras estructuras pueden ayudar a caracterizarlos.
3. **Granularidad:** la suma debe usar la misma agregación temporal, zona horaria y criterio de calidad.
4. **Duplicación de fuentes:** no se deben sumar Baixo Iguaçu y una estación aguas abajo que ya incluya ese aporte.
5. **Balance físico:** como control de calidad, verificar relaciones aproximadas entre afluencia, defluencia, turbinada, vertida, otras estructuras y variación de almacenamiento.
6. **Identidad de reservatorios:** la API usa `Identificador`; se debe construir una tabla de equivalencias explícita con los códigos del Parquet y del catálogo local. No asumir que nombre corto y código local son intercambiables.

## 7. Riesgos y controles necesarios

### Riesgos de usar solamente la API

- Caída, latencia o cambios de contrato del servicio.
- Expiración del token o pérdida de autorización SINTEGRE.
- Imposibilidad de reconstruir un histórico anterior a la ventana operativa.
- Correcciones retroactivas no detectadas si solo se consulta el último valor.
- Diferencias entre `TRL`, `CON`, `COO` y el dato publicado en Parquet.
- Límites de paginación: 240 elementos por página; una serie horaria de 7 días requiere al menos 1 página, pero varias métricas y reservatorios multiplican las llamadas.
- Ausencia, en la especificación entregada, de límites de tasa, SLA, esquema de reintentos y política de retención.

### Controles recomendados

- Guardar `source`, `quality`, `origin`, `requested_at`, `received_at`, `api_version` y parámetros de consulta junto con cada registro.
- Reintentos limitados con backoff para errores transitorios, sin ocultar errores definitivos.
- Alerta visible de antigüedad de datos y estado de autenticación.
- Conservación del último dato válido y del Parquet como fallback, marcando claramente que es un fallback.
- Prueba automática de consistencia de unidades, duplicados, timestamps y valores negativos/imposibles.
- Comparación diaria API-Parquet durante la fase piloto.
- No guardar usuario, contraseña ni tokens en el repositorio; usar variables de entorno o un almacén de secretos.

## 8. Arquitectura recomendada

### Capa 1: adquisición

Crear un adaptador ONS API que:

1. Autentique y renueve el token.
2. Consulte el catálogo y mantenga el mapeo de identificadores.
3. Obtenga cada 10-30 minutos las grandezas horarias de los reservatorios críticos.
4. Consulte precipitación y previsiones con frecuencias separadas.
5. Registre errores, latencia, código HTTP y cantidad de resultados.

### Capa 2: almacenamiento normalizado

Persistir una tabla de observaciones con, como mínimo:

```text
reservatorio_id
timestamp
variable
valor
unidad
intervalo
origem
qualidade
fuente
consultado_en
```

Usar una clave única `(reservatorio_id, timestamp, variable, intervalo, origem, qualidade)` o una política de versión equivalente. El `upsert` debe permitir que un valor preliminar sea reemplazado por uno consolidado sin destruir la trazabilidad.

### Capa 3: serving del panel

El panel debe leer una vista unificada:

- API para los datos recientes cuando estén disponibles y validados.
- Parquet/SQLite para histórico y fallback.
- Indicador visible de fuente y antigüedad.
- Cálculo del aporte a Yacyretá solo con puntos y calidades compatibles.

### Capa 4: histórico y respaldo

Mantener la descarga mensual Parquet incluso después de habilitar la API. El proceso debe conservar los archivos originales y un manifiesto con URL, tamaño, fecha de descarga y hash. Esto permite auditar diferencias y reconstruir series.

## 9. Plan de adopción

### Fase 0: prueba de acceso (1 día)

- Confirmar autorización de `IntegracaoHidrologia` en SINTEGRE.
- Obtener catálogo de reservatorios.
- Identificar Itaipú, Baixo Iguaçu, puntos del Iguazú y estaciones de interés.
- Probar autenticación, renovación, paginación y manejo de errores.

### Fase 1: piloto paralelo (7-14 días)

- Consultar API y Parquet/S3 sin cambiar el valor mostrado al operador.
- Comparar AFL, DFL, TUR, VER, niveles y volumen útil.
- Medir frescura, latencia, tasa de error y divergencias.
- Clasificar diferencias por origen/calidad/agregación, no solo por valor numérico.

### Fase 2: uso operativo controlado

- Usar API para datos de las últimas 24-48 horas si cumple los umbrales acordados.
- Mantener Parquet como fallback automático.
- Incorporar indicador de fuente y estado de sincronización.

### Fase 3: explotación ampliada

- Incorporar previsiones de caudal y precipitación.
- Construir indicadores de tendencia, almacenamiento, vertimiento y energía turbinable.
- Calibrar el desfase de tránsito hacia Yacyretá y documentar el balance.

## 10. Criterios de aceptación sugeridos

Antes de considerar la API apta para operación:

- Disponibilidad efectiva >= 99% durante el piloto, o el objetivo acordado por el área.
- Mediana de latencia de consulta compatible con el refresco del panel.
- Tasa de respuestas válidas >= 99% para las variables críticas.
- Cero credenciales o tokens expuestos en código, logs o archivos versionados.
- Coincidencia explicada para al menos 95% de los puntos comparables API-Parquet; el 5% restante debe quedar clasificado por desfase, calidad o corrección.
- Fallback local probado con la API inaccesible, token expirado y respuesta incompleta.
- Balance y unidades validados por Hidrología antes de activar alertas basadas en la suma de caudales.

## 11. Conclusión

**Sí conviene adoptar la API como fuente principal del sitio**, porque el objetivo es consultar datos actuales y no construir un histórico local obligatorio. El Parquet queda como recurso opcional para históricos, auditoría o recuperación manual, mientras que la caché local mantiene continuidad operativa durante interrupciones breves.

La decisión recomendada para Hidrología de Yacyretá es, por tanto:

> **API ONS para actualidad y previsiones externas + caché local para continuidad operativa + Parquet ONS como recurso histórico opcional.**

La primera implementación debería ser un piloto paralelo de 7-14 días. El indicador de aporte a Yacyretá debe retirarse del tablero operativo hasta contar con una medición directa o una metodología hidrológica validada. Las previsiones deben mostrarse únicamente si provienen de la API, separadas de las observaciones y con su organismo, emisión y validez.

El detalle técnico y el orden de ejecución están documentados en [PLAN_IMPLEMENTACION_API_ONS_YACYRETA.md](./PLAN_IMPLEMENTACION_API_ONS_YACYRETA.md).
