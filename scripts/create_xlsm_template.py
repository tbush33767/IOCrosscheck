"""One-time script: create the .xlsm template with embedded VBA macros.

Run this once to generate src/io_crosscheck/templates/crosscheck_template.xlsm.
Requires Excel installed and pywin32.
"""
import os
import sys
import time
import win32com.client as win32

TEMPLATE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "src", "io_crosscheck", "templates"
)
TEMPLATE_PATH = os.path.abspath(os.path.join(TEMPLATE_DIR, "crosscheck_template.xlsm"))

# ---------------------------------------------------------------------------
# VBA source code
# ---------------------------------------------------------------------------

# ThisWorkbook module — initialization
VBA_THIS_WORKBOOK = r"""
Private Sub Workbook_Open()
    ' Initialize CopyEnabled flag if not set
    Dim ws As Worksheet
    Set ws = Me.Sheets("Summary")
    If ws.Range("E1").Value = "" Then
        ws.Range("E1").Value = "CopyEnabled"
        ws.Range("F1").Value = True
    End If
End Sub
"""

# Verification Detail sheet module — click-to-copy + versioning
VBA_SHEET_DETAIL = r"""
Private Sub Worksheet_SelectionChange(ByVal Target As Range)
    ' Click-to-copy: copy selected cell value to clipboard
    On Error Resume Next
    Dim copyEnabled As Boolean
    copyEnabled = ThisWorkbook.Sheets("Summary").Range("F1").Value
    If Not copyEnabled Then Exit Sub
    If Target.Cells.Count <> 1 Then Exit Sub
    If Target.Row < 2 Then Exit Sub
    If Trim(Target.Value & "") = "" Then Exit Sub

    Dim obj As New DataObject
    obj.SetText CStr(Target.Value)
    obj.PutInClipboard
    Application.StatusBar = "Copied: " & Left(CStr(Target.Value), 80)

    ' Clear status bar after a moment via OnTime
    Application.OnTime Now + TimeValue("00:00:02"), "ClearStatusBar"
    On Error GoTo 0
End Sub

Private Sub Worksheet_Change(ByVal Target As Range)
    ' Row versioning: track every edit in data rows
    On Error Resume Next
    If Target.Row < 2 Then Exit Sub

    ' Prevent recursion
    Application.EnableEvents = False

    Dim ws As Worksheet
    Set ws = Me
    Dim versionCol As Long
    versionCol = 0

    ' Find the Version column
    Dim c As Range
    For Each c In ws.Range("1:1")
        If c.Value = "Version" Then
            versionCol = c.Column
            Exit For
        End If
        If c.Column > 50 Then Exit For
    Next c

    If versionCol = 0 Then
        Application.EnableEvents = True
        Exit Sub
    End If

    ' Process each changed cell
    Dim cell As Range
    For Each cell In Target
        If cell.Row >= 2 And cell.Column <> versionCol Then
            ' Increment version
            Dim currentVer As Long
            currentVer = Val(ws.Cells(cell.Row, versionCol).Value)
            currentVer = currentVer + 1
            ws.Cells(cell.Row, versionCol).Value = currentVer

            ' Log to Version Log sheet
            Dim logSheet As Worksheet
            Set logSheet = ThisWorkbook.Sheets("Version Log")
            Dim nextRow As Long
            nextRow = logSheet.Cells(logSheet.Rows.Count, 1).End(xlUp).Row + 1

            logSheet.Cells(nextRow, 1).Value = Now  ' Timestamp
            logSheet.Cells(nextRow, 2).Value = cell.Row  ' Row
            logSheet.Cells(nextRow, 3).Value = ws.Cells(1, cell.Column).Value  ' Column name
            logSheet.Cells(nextRow, 4).Value = ""  ' Old value (not easily captured without class module)
            logSheet.Cells(nextRow, 5).Value = cell.Value  ' New value
            logSheet.Cells(nextRow, 6).Value = currentVer  ' Version
        End If
    Next cell

    Application.EnableEvents = True
    On Error GoTo 0
End Sub
"""

# Standard module — helper functions
VBA_MODULE = r"""
Sub ClearStatusBar()
    Application.StatusBar = False
End Sub

Sub ToggleCopyMode()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Sheets("Summary")
    Dim current As Boolean
    current = ws.Range("F1").Value
    ws.Range("F1").Value = Not current
    If ws.Range("F1").Value Then
        MsgBox "Click-to-Copy: ENABLED" & vbCrLf & vbCrLf & _
               "Click any cell in the Verification Detail sheet to copy its value.", _
               vbInformation, "IO Crosscheck"
    Else
        MsgBox "Click-to-Copy: DISABLED", vbInformation, "IO Crosscheck"
    End If
End Sub
"""


def create_template():
    os.makedirs(TEMPLATE_DIR, exist_ok=True)

    # Remove old template if exists
    if os.path.exists(TEMPLATE_PATH):
        os.remove(TEMPLATE_PATH)

    # Kill any existing Excel instances so the trust setting takes effect
    import subprocess
    subprocess.run(["taskkill", "/f", "/im", "EXCEL.EXE"],
                   capture_output=True)
    time.sleep(2)

    excel = win32.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False

    try:
        wb = excel.Workbooks.Add()

        # --- Rename Sheet1 to "Verification Detail" ---
        ws_detail = wb.Sheets(1)
        ws_detail.Name = "Verification Detail"

        # --- Create sheets in desired order ---
        # Order: Verification Detail, Conflicts, Summary, Version Log

        ws_conflicts = wb.Sheets.Add(After=wb.Sheets(wb.Sheets.Count))
        ws_conflicts.Name = "Conflicts"

        ws_summary = wb.Sheets.Add(After=wb.Sheets(wb.Sheets.Count))
        ws_summary.Name = "Summary"
        ws_summary.Range("E1").Value = "CopyEnabled"
        ws_summary.Range("F1").Value = True

        # Add toggle button via OLEObjects
        try:
            btn = ws_summary.OLEObjects.Add(
                ClassType="Forms.CommandButton.1",
                Left=400, Top=10, Width=140, Height=30,
            )
            btn.Object.Caption = "Toggle Copy Mode"
            btn.Name = "btnToggleCopy"
        except Exception as e:
            print(f"WARNING: Could not add button: {e}. Add manually in Excel.")

        ws_log = wb.Sheets.Add(After=wb.Sheets(wb.Sheets.Count))
        ws_log.Name = "Version Log"
        log_headers = ["Timestamp", "Row", "Column", "Old Value", "New Value", "Version"]
        for i, h in enumerate(log_headers, start=1):
            ws_log.Cells(1, i).Value = h
            ws_log.Cells(1, i).Font.Bold = True

        # --- Delete extra default sheets ---
        for i in range(wb.Sheets.Count, 0, -1):
            s = wb.Sheets(i)
            if s.Name not in ("Verification Detail", "Summary", "Conflicts", "Version Log"):
                s.Delete()

        # --- Inject VBA ---
        # ThisWorkbook
        tb_module = wb.VBProject.VBComponents("ThisWorkbook")
        tb_module.CodeModule.AddFromString(VBA_THIS_WORKBOOK)

        # Verification Detail sheet code
        detail_module = wb.VBProject.VBComponents(ws_detail.CodeName)
        detail_module.CodeModule.AddFromString(VBA_SHEET_DETAIL)

        # Standard module
        std_module = wb.VBProject.VBComponents.Add(1)  # vbext_ct_StdModule
        std_module.Name = "modHelpers"
        std_module.CodeModule.AddFromString(VBA_MODULE)

        # --- Add MSForms reference for DataObject (clipboard) ---
        # The DataObject requires FM20.DLL reference
        try:
            wb.VBProject.References.AddFromFile(
                r"C:\Windows\SysWOW64\FM20.DLL"
            )
        except Exception:
            try:
                wb.VBProject.References.AddFromFile(
                    r"C:\Windows\System32\FM20.DLL"
                )
            except Exception:
                print("WARNING: Could not add FM20.DLL reference. "
                      "Click-to-copy may need manual reference to "
                      "'Microsoft Forms 2.0 Object Library'.")

        # --- Save as .xlsm ---
        # 52 = xlOpenXMLWorkbookMacroEnabled
        wb.SaveAs(TEMPLATE_PATH, FileFormat=52)
        print(f"Template created: {TEMPLATE_PATH}")

    finally:
        wb.Close(SaveChanges=False)
        excel.Quit()
        time.sleep(1)


if __name__ == "__main__":
    create_template()
