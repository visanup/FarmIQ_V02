import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputPath = process.argv[2];
if (!outputPath) throw new Error("Usage: node create_performance_standard_template.mjs <output.xlsx>");

const workbook = Workbook.create();
const guide = workbook.worksheets.add("Instructions");
const standards = workbook.worksheets.add("Standards");
const font = { name: "Arial", size: 10 };

guide.showGridLines = false;
guide.getRange("A2").values = [["Broiler performance standard template"]];
guide.getRange("A2").format = { font: { name: "Arial", size: 14, bold: true, color: "#1F2937" } };
guide.getRange("A4:B9").values = [
  ["Purpose", "One approved daily growth curve per breed and sex."],
  ["Required rows", "One row for each breed, sex, and age_days from day 1 onward."],
  ["Sex values", "as_hatched, male, female"],
  ["Approval", "Only rows with status = APPROVED may be used for model training or edge packages."],
  ["Source", "Record the publisher, document version, and effective date for every curve."],
  ["File use", "Save a copy with a descriptive name, then pass it using --performance-standard."],
];
guide.getRange("A4:A9").format = { fill: "#E8F0F8", font: { name: "Arial", bold: true, color: "#1F2937" } };
guide.getRange("A4:B9").format.borders = { preset: "outside", style: "thin", color: "#CBD5E1" };
guide.getRange("A:A").format.columnWidth = 20;
guide.getRange("B:B").format.columnWidth = 88;
guide.getRange("A2:B9").format.verticalAlignment = "center";

standards.showGridLines = false;
standards.getRange("A2").values = [["Approved daily broiler growth standards"]];
standards.getRange("A2").format = { font: { name: "Arial", size: 14, bold: true, color: "#1F2937" } };
standards.getRange("A3").values = [["Enter only approved reference values. Leave template rows blank until a source has been approved."]];
standards.getRange("A3").format = { font: { name: "Arial", size: 10, italic: true, color: "#475569" } };
const headers = [["standard_id", "breed", "sex", "age_days", "body_weight_g", "daily_gain_g", "adg_g_per_day", "cumulative_feed_g", "fcr", "source", "source_version", "effective_date", "approved_by", "status", "notes"]];
standards.getRange("A5:O5").values = headers;
standards.getRange("A5:O5").format = { fill: "#1F4E78", font: { name: "Arial", bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
standards.getRange("A6:O55").format = { fill: "#FFF8D6", font, verticalAlignment: "center" };
standards.getRange("A5:O55").format.borders = { preset: "outside", style: "thin", color: "#CBD5E1" };
standards.getRange("D6:D55").dataValidation = { rule: { type: "whole", operator: "between", formula1: 1, formula2: 365 } };
standards.getRange("C6:C55").dataValidation = { rule: { type: "list", values: ["as_hatched", "male", "female"] } };
standards.getRange("N6:N55").dataValidation = { rule: { type: "list", values: ["DRAFT", "APPROVED", "RETIRED"] } };
standards.getRange("D6:H55").format.numberFormat = "#,##0.0";
standards.getRange("I6:I55").format.numberFormat = "0.000";
standards.getRange("L6:L55").format.numberFormat = "yyyy-mm-dd";
standards.getRange("A:A").format.columnWidth = 18;
standards.getRange("B:B").format.columnWidth = 24;
standards.getRange("C:C").format.columnWidth = 14;
standards.getRange("D:I").format.columnWidth = 15;
standards.getRange("J:K").format.columnWidth = 28;
standards.getRange("L:N").format.columnWidth = 16;
standards.getRange("O:O").format.columnWidth = 38;
standards.freezePanes.freezeRows(5);

workbook.recalculate();
await fs.mkdir(path.dirname(outputPath), { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
const inspection = await workbook.inspect({ kind: "table", range: "Standards!A2:O10", include: "values,formulas", tableMaxRows: 10, tableMaxCols: 15 });
console.log(inspection.ndjson);
