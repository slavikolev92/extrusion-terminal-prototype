from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTUALS = ROOT / "interim-costing-process/excel-tools/actuals-capture/actuals-capture-installer.bas"


def macro_text() -> str:
    return ACTUALS.read_text(encoding="utf-8")


def procedure_body(text: str, declaration: str) -> str:
    start = text.index(declaration)
    possible_ends = [
        position
        for position in [
            text.find("End Function", start),
            text.find("End Sub", start),
        ]
        if position != -1
    ]
    end = min(possible_ends)
    return text[start:end]


def test_actuals_capture_owns_expected_sheets():
    text = macro_text()
    for sheet in [
        "Actuals Entry",
        "Actuals Review",
        "Actuals Validation",
        "ActualsData",
        "ActualsStatus",
        "ActualsConfig",
    ]:
        assert sheet in text


def test_actuals_install_preserves_existing_workbook_template():
    text = macro_text()
    body = procedure_body(text, "Public Sub InstallActualsCapture")
    assert "ActualsWorkbookTemplateExists" in body
    assert "Existing Actuals workbook template preserved" in body
    assert body.index("ActualsWorkbookTemplateExists") < body.index("SetupActualsEntry")
    preserve_body = procedure_body(text, "Private Function ActualsWorkbookTemplateExists")
    assert 'Range("F1").Value)) = "Actuals Setup"' in preserve_body
    assert 'Range("D2").Value)) = "Saved active actual cards for loaded order"' in preserve_body
    assert 'Range("A1").Value)) = "Actual card ID"' in preserve_body
    assert 'Range("A1").Value)) = "Production order"' in preserve_body


def test_actuals_config_defines_cutoff_and_inclusion_tables():
    text = macro_text()
    assert "WorkbookConfig" in text
    assert "ExplicitInclusions" in text
    assert "FirstIncludedRow" in text
    assert "FirstIncludedProductionOrder" in text
    assert "SetActualsCutoffFromPrompt" in text
    assert "Enter the first Database row to include in Actuals V1" in text
    assert "This is the cutoff. Rows at and below this Database row are included." in text
    example_body = procedure_body(text, "Private Function ConfigExampleRowCanBeWritten")
    assert 'LCase$(Trim$(CStr(ws.Range("A7").Value))) = "example"' in example_body


def test_actuals_validation_checks_duplicates_inside_included_set():
    text = macro_text()
    assert "ValidateDuplicateIncludedProductionOrders" in text
    assert "Duplicate production order number in included Actuals row set" in text


def test_actuals_validation_generates_report_sheet_and_activates_it():
    text = macro_text()
    body = procedure_body(text, "Public Sub RunActualsValidation")
    assert "ws.Cells.Clear" in body
    assert "WriteActualsValidationHeader" in body
    assert "ValidateDuplicateIncludedProductionOrders" in body
    assert "ValidateCompletedIncludedOrders" in body
    assert "ValidateActualCards" in body
    assert "WriteActualsValidationReport" in body
    assert "ws.Activate" in body


def test_actuals_duplicate_validation_only_scans_included_scope():
    text = macro_text()
    body = procedure_body(text, "Private Sub ValidateDuplicateIncludedProductionOrders")
    assert "Set inclusions = LoadExplicitInclusions()" in body
    assert "RowIsInActualsScope(rowNumber, productionOrder, inclusions)" in body
    assert "duplicateReported" in body
    assert "Database rows " in body
    assert "Duplicate production order number in included Actuals row set." in body


def test_actuals_completed_orders_require_active_cards_for_expected_operations():
    text = macro_text()
    body = procedure_body(text, "Private Sub ValidateCompletedIncludedOrders")
    assert "ProductionOrderStatus(productionOrder) = \"Completed\"" in body
    assert "ExpectedOperationsForDatabaseRow(rowNumber)" in body
    assert "ExpectedOperationCodesForDatabaseRow(rowNumber)" in body
    assert "ActiveActualCardExists(productionOrder, operationCode" in body
    assert "Completed production order is missing an active ActualsData card for an expected operation." in body
    active_body = procedure_body(text, "Private Function ActiveActualCardExists")
    assert "Not ActualCardIsVoided(rowNumber)" in active_body
    assert "ActualsDataRowIsInCurrentScope(rowNumber)" in active_body
    assert "Trim$(CStr(ws.Cells(rowNumber, 1).Value)) <> excludedCardId" in active_body


def test_actuals_card_validation_enforces_task_12_rules():
    text = macro_text()
    body = procedure_body(text, "Private Sub ValidateActualCards")
    assert "ActualsDataRowIsInCurrentScope(rowNumber)" in body
    assert "ActualCardIsActive(rowNumber)" in body
    assert "OrderExpectsOperation(databaseRow, operationCode)" in body
    assert "Saved actual operation is no longer expected for its production order." in body
    assert "Required time fields are missing." in body
    assert "Stop datetime cannot be before start datetime." in body
    assert "Numeric fields must be non-negative." in body
    assert "PP film material and quantity must be entered together." in body
    assert "Total minutes override requires a reason." in body
    assert "Confection operations require units." in body
    assert "CDate(ws.Cells(rowNumber, 13).Value) < CDate(ws.Cells(rowNumber, 12).Value)" in body
    assert "ws.Cells(rowNumber, 17).Value" in body
    assert "ws.Cells(rowNumber, 18).Value" in body
    assert "ws.Cells(rowNumber, 28).Value" in body
    time_body = procedure_body(text, "Private Function ActualCardHasRequiredTimeFields")
    for column in [8, 9, 10, 11, 12, 13]:
        assert f"ws.Cells(dataRow, {column}).Value" in time_body
    numeric_body = procedure_body(text, "Private Function ActualCardNumericFieldsAreNonNegative")
    assert "Array(14, 15, 16, 17, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 30)" in numeric_body
    pp_body = procedure_body(text, "Private Function ActualCardPPFilmFieldsArePaired")
    assert "ws.Cells(dataRow, 29).Value" in pp_body
    assert "ws.Cells(dataRow, 30).Value" in pp_body


def test_actuals_capture_does_not_install_database_events_or_write_actuals_to_database():
    text = macro_text()
    assert "Worksheet_BeforeDoubleClick" not in text
    assert "Worksheet_Change" not in text
    assert "Workbook_SheetBeforeDoubleClick" not in text

    write_body = procedure_body(text, "Private Function WriteActualCardRow")
    status_body = procedure_body(text, "Private Sub UpsertProductionOrderStatus")
    assert "DATABASE_SHEET_NAME" not in write_body
    assert "DATABASE_SHEET_NAME" not in status_body


def test_actuals_installer_removes_actuals_sheet_protection_and_password_friction():
    text = macro_text()
    assert "Public Sub ApplyActualsProtection" in text

    body = procedure_body(text, "Public Sub ApplyActualsProtection")
    assert "UnprotectActualsSheet" in body
    assert "Password:=LEGACY_PROTECTION_PASSWORD" in text
    assert ".Protect Password:=" not in text
    assert "UserInterfaceOnly:=True" not in text
    assert "SHEET_PASSWORD" not in text
    assert "ws.Cells.Locked = False" in text


def test_actuals_operation_flags_trim_and_accept_lowercase_da():
    text = macro_text()
    assert "OperationFlagIsYes" in text
    assert 'LCase$(Trim$(' in text
    assert '"да"' in text


def test_actuals_capture_calculates_time_and_net_quantities_on_save():
    text = macro_text()
    assert "TryParseNonNegativeNumber" in text
    assert "CalculatedNetKg" in text
    assert "TotalMinutesForOperation" in text
    assert "ValidateActualEntryCalculations" in text
    assert text.count("ValidateActualEntryCalculations") >= 3
    assert "Private Function WriteActualCardRow" in text
    assert "If Not WriteActualCardRow" in text
    write_body = procedure_body(text, "Private Function WriteActualCardRow")
    assert "Exit Sub" not in write_body
    assert "Exit Function" in write_body
    assert "ws.Cells(dataRow, 12).Value = startAt" in text
    assert "ws.Cells(dataRow, 13).Value = stopAt" in text
    assert "ws.Cells(dataRow, 16).Value = calculatedTotalMinutes" in text
    assert "ws.Cells(dataRow, 19).Value = totalMinutes" in text
    assert "ws.Cells(dataRow, 23).Value = calculatedNetKgValue" in text
    assert "ws.Cells(dataRow, 25).Value = netKg" in text
    assert "Calculated total minutes cannot be negative." in text
    assert "Calculated net kg cannot be negative." in text


def test_actuals_capture_blocks_invalid_time_and_override_reason():
    text = macro_text()
    assert "Stop datetime cannot be before start datetime." in text
    assert "Total minutes override requires a reason." in text
    assert "CombineEntryDateTime" in text


def test_actuals_config_supports_working_calendar_defaults():
    text = macro_text()
    assert "WorkingCalendar" in text
    assert "WorkingMinutesBetween" in text
    assert "DefaultWorkingDayMinutes" in text
    assert "DefaultWorkStartTime" in text
    assert "DefaultWorkStopTime" in text
    assert "Malformed ActualsConfig WorkingCalendar row" in text
    assert "Workday rows require valid StartTime and StopTime." in text
    assert "StopTime must be later than StartTime." in text
    assert "workingMinutesError" in text
    assert "Err.Raise" not in procedure_body(text, "Private Function WorkingWindowForDate")


def test_actuals_review_installs_refresh_save_and_validation_buttons():
    text = macro_text()
    setup_start = text.index("Private Sub SetupActualsReview")
    setup_end = text.index("Private Sub SetupActualsValidation", setup_start)
    setup_body = text[setup_start:setup_end]
    for macro_name in [
        "RefreshActualsReview",
        "SaveActualsReview",
        "RunActualsValidation",
    ]:
        assert macro_name in setup_body
    assert "AddActualsReviewButton" in text


def test_actuals_review_uses_included_scope_and_status_sheet_only():
    text = macro_text()
    refresh_body = procedure_body(text, "Public Sub RefreshActualsReview")
    assert "LoadExplicitInclusions" in refresh_body
    assert "RowIsInActualsScope" in text
    assert "FirstIncludedRow() To lastRow" in refresh_body
    assert "5 To lastRow" not in refresh_body
    assert "ActualsDataRowIsInCurrentScope" in text
    assert "WriteActualsReviewRow" in text
    save_body = procedure_body(text, "Public Sub SaveActualsReview")
    assert "UpsertProductionOrderStatus" in save_body
    assert "STATUS_SHEET_NAME" in text
    assert "DATABASE_SHEET_NAME" not in save_body


def test_actuals_review_save_requires_generated_marker_and_included_scope():
    text = macro_text()
    assert "ActualsReviewDataRow" in text
    assert "ws.Cells(outputRow, 11).Value = \"ActualsReviewDataRow\"" in text
    assert 'ws.Columns("K").Hidden = True' in text
    status_row_body = procedure_body(text, "Private Function IsActualsReviewStatusRow")
    assert "Cells(rowNumber, 11)" in status_row_body
    assert "ActualsReviewDataRow" in status_row_body
    save_body = procedure_body(text, "Public Sub SaveActualsReview")
    assert "IncludedDatabaseRowsForOrder(productionOrder)" in text
    assert "ValidateActualsReviewStatusScope" in save_body
    assert "Actuals Review row is no longer in the current included Actuals scope" in text


def test_actuals_review_save_validates_status_before_upsert():
    text = macro_text()
    assert "ApprovedActualsStatuses" in text
    assert "StatusIsApproved" in text
    assert "Invalid Manufacturing status" in text
    assert "ActualsConfig StatusList" in text
    save_body = procedure_body(text, "Public Sub SaveActualsReview")
    assert "If Not StatusIsApproved(statusValue)" in save_body
    assert save_body.index("If Not StatusIsApproved(statusValue)") < save_body.index("UpsertProductionOrderStatus")


def test_actuals_review_refresh_styles_and_unprotects_after_rebuilding_sheet():
    text = macro_text()
    refresh_body = procedure_body(text, "Public Sub RefreshActualsReview")
    assert "ws.Range(\"A1:K\" & CStr(ws.Rows.Count)).Clear" in refresh_body
    assert "StyleActualsReviewShell ws" in refresh_body
    assert "UnprotectActualsSheet ws" in refresh_body
    assert refresh_body.index("StyleActualsReviewShell ws") > refresh_body.index("WriteActualsReviewTable")
    assert refresh_body.index("UnprotectActualsSheet ws") > refresh_body.index("WriteActualsReviewTable")


def test_actuals_review_headers_and_default_tables_match_spec():
    text = macro_text()
    for expected in [
        "In Production / On Hold",
        "Planned",
        "Production order",
        "Customer",
        "Product/type",
        "Manufacturing status",
        "Operations entered / expected",
        "Gross ordered kg",
        "Finished product actual gross kg",
        "Finished product actual net kg",
        "Finished product actual meters",
        "Finished product actual units",
    ]:
        assert expected in text
    refresh_body = procedure_body(text, "Public Sub RefreshActualsReview")
    assert 'reviewRows("In Production / On Hold")' in refresh_body
    assert 'reviewRows("Planned")' in refresh_body
    assert "SortReviewRowsByProductionOrder" in text
