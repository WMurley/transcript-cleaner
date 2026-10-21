' Opens the Transcript Cleaner app with no console window.
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dir
root = fso.GetParentFolderName(dir)  ' the install folder, where setup put Python
sh.Run """" & root & "\.venv\Scripts\pythonw.exe"" """ & dir & "\app.py""", 0, False
