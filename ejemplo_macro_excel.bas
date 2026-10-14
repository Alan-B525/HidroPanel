Attribute VB_Name = "ModuloCopel"
Option Explicit

' ==============================================================================
' MACRO PARA EXCEL: Descargar e importar datos de COPEL MHB y ENGIE
' Llama al ejecutable 'descargar_copel.exe' para actualizar los archivos TXT
' en la misma carpeta del libro de Excel.
' ==============================================================================

Public Sub EjecutarDescargaTXT()
    Dim wsh As Object
    Dim fso As Object
    Dim rutaExe As String
    Dim cmd As String
    Dim resultado As Long
    
    ' 1. El ejecutable se busca en la misma carpeta que este libro de Excel
    rutaExe = ThisWorkbook.Path & "\descargar_copel.exe"
    
    Set fso = CreateObject("Scripting.FileSystemObject")
    
    If Not fso.FileExists(rutaExe) Then
        MsgBox "No se encontró el archivo: " & vbCrLf & rutaExe & vbCrLf & vbCrLf & _
               "Asegúrate de colocar 'descargar_copel.exe' en la misma carpeta que este Excel.", _
               vbCritical, "Error: Ejecutable no encontrado"
        Exit Sub
    End If
    
    ' 2. Ejecutar 'descargar_copel.exe'
    ' El ejecutable guarda automáticamente los archivos TXT en su misma carpeta.
    ' Usamos 1 para ver la consola brevemente (o 0 para ocultarla en segundo plano)
    Set wsh = CreateObject("WScript.Shell")
    cmd = """" & rutaExe & """"
    
    Application.StatusBar = "Descargando datos actualizados de COPEL y ENGIE..."
    resultado = wsh.Run(cmd, 1, True)
    
    If resultado <> 0 Then
        MsgBox "Ocurrió un error al ejecutar la descarga (Código: " & resultado & ").", vbExclamation, "Error"
        Application.StatusBar = False
        Exit Sub
    End If
    
    Application.StatusBar = False
    MsgBox "¡Archivos TXT actualizados con éxito en la carpeta del libro!", vbInformation, "Descarga Completada"
End Sub
