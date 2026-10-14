# Subproyecto Copel & Engie - Extractor Hidrológico

Extractor automatizado de telemetría hidrológica para la cuenca del Río Iguazú a partir de dos fuentes oficiales:
1. **COPEL MHB**: `https://www.copel.com/mhbweb/paginas/bacia-iguacu.jsf`
2. **ENGIE Brasil** (ex-Tractebel): `https://www.engie.com.br/reservatorios/`

---

## 🎯 Salida en Archivos TXT (Compatible con Macros de Excel)

El script y el ejecutable independiente **[`descargar_copel.exe`](file:///c:/Users/drodich/Documents/URL-agep/descargar_copel.exe)** generan directamente los archivos `.txt` en la misma carpeta donde se ejecutan, reemplazando los existentes:

| Fuente | Estación / Central | Archivos de Salida Generados | Formato de Columnas |
| :--- | :--- | :--- | :--- |
| **COPEL** | Cataratas | `Cataratas.txt` | `Fecha/Hora \t Regla \t Caudal` |
| **COPEL** | Porto Capanema | `Capanema.txt` | `Fecha/Hora \t Regla \t Caudal \t Lluvia \t Lluvia Acum` |
| **COPEL** | Baixo Iguaçu | `Baixo Iguazú.txt` / `Baixo Iguazu.txt` | `Fecha/Hora \t Nivel \t Vol% \t Jusante \t Afluente \t Turb \t Vert \t Defl` |
| **COPEL** | Salto Caxias | `Caxias.txt` | 10 columnas tabuladas |
| **COPEL** | Segredo | `segredo.txt` | 10 columnas tabuladas |
| **COPEL** | Foz do Areia | `Areia.txt` | 10 columnas tabuladas |
| **ENGIE** | Salto Osório | `TRACTEBEL Salto OSORIO.txt` / `OSORIO.txt` | `FechaHora \t Nivel \t Vol% \t Afluente \t Turb \t Vert \t Defl` |
| **ENGIE** | Salto Santiago | `TRACTEBEL Salto SANTIAGO.txt` / `SANTIAGO.txt` | `FechaHora \t Nivel \t Vol% \t Afluente \t Turb \t Vert \t Defl` |

---

## ⏱️ Regla de Fechas
*   **Filtro:** Desde **hace 2 días a las 00:00:00 hs** hasta la última hora actual disponible.
*   **Orden:** Cronológico inverso (más reciente arriba, hacia atrás en el tiempo).
*   **Separador:** Tabulación (`\t`), sin encabezados y con saltos de línea Windows (`CRLF`).

---

## 💻 Integración con Excel (Macro VBA)

Solo colocas **`descargar_copel.exe`** en la misma carpeta que tu libro de Excel (`.xlsm`).

Desde tu macro ejecutas:
```vba
Dim wsh As Object
Set wsh = CreateObject("WScript.Shell")

' Ejecuta y espera a que termine (el 0 oculta la consola)
wsh.Run """" & ThisWorkbook.Path & "\descargar_copel.exe""", 0, True

' A continuación tu macro ya puede leer Cataratas.txt, Areia.txt, etc.
```
