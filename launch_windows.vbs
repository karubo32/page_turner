' Page Turner GUI launcher (Windows)
'
' Resolves the full path to pythonw.exe before launching.
' PATH often contains a Microsoft Store app-execution alias: a 0-byte
' pythonw.exe stub that exits immediately without starting anything.
' Those stubs are skipped by checking the file size.
'
' NOTE: keep this file ASCII-only with CRLF line endings.
'       WSH reads .vbs as ANSI and rejects a UTF-8 BOM, so non-ASCII
'       characters here would break the script.

Option Explicit

Dim fso, shell, scriptDir, target, pyw, msg

Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
target    = fso.BuildPath(scriptDir, "gui\page_turner_gui.py")

If Not fso.FileExists(target) Then
  msg = "GUI script not found:" & vbCrLf & vbCrLf & target
  MsgBox msg, vbCritical, "Page Turner"
  WScript.Quit 1
End If

pyw = FindPythonW()

If pyw = "" Then
  msg = "pythonw.exe was not found." & vbCrLf & vbCrLf
  msg = msg & "Install Python from python.org and enable" & vbCrLf
  msg = msg & "'Add Python to PATH' during installation."
  MsgBox msg, vbCritical, "Page Turner"
  WScript.Quit 1
End If

shell.CurrentDirectory = scriptDir
shell.Run """" & pyw & """ """ & target & """", 0, False


' Locate pythonw.exe. Returns "" when nothing usable is found.
Function FindPythonW()
  Dim dirs, cand, i

  FindPythonW = ""

  ' 1) Search PATH in order.
  dirs = Split(shell.ExpandEnvironmentStrings("%PATH%"), ";")
  For i = 0 To UBound(dirs)
    cand = ProbePythonW(Trim(dirs(i)))
    If cand <> "" Then
      FindPythonW = cand
      Exit Function
    End If
  Next

  ' 2) Fall back to common machine-wide install locations.
  dirs = Array("C:\Python313", "C:\Python312", "C:\Python311", "C:\Python310")
  For i = 0 To UBound(dirs)
    cand = ProbePythonW(dirs(i))
    If cand <> "" Then
      FindPythonW = cand
      Exit Function
    End If
  Next

  ' 3) Fall back to common per-user install locations.
  dirs = Array("Python313", "Python312", "Python311", "Python310")
  For i = 0 To UBound(dirs)
    cand = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\")
    cand = ProbePythonW(cand & dirs(i))
    If cand <> "" Then
      FindPythonW = cand
      Exit Function
    End If
  Next
End Function


' Return the full path to a real pythonw.exe in the given folder, or "".
Function ProbePythonW(folder)
  Dim cand

  ProbePythonW = ""
  If folder = "" Then Exit Function

  cand = fso.BuildPath(folder, "pythonw.exe")
  If Not fso.FileExists(cand) Then Exit Function

  ' A 0-byte file is a Microsoft Store stub - it never actually runs.
  If fso.GetFile(cand).Size = 0 Then Exit Function

  ProbePythonW = cand
End Function
