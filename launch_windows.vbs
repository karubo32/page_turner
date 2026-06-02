Dim fso, shell, scriptDir
Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.Run "pythonw """ & scriptDir & "\gui\page_turner_gui.py""", 0, False
