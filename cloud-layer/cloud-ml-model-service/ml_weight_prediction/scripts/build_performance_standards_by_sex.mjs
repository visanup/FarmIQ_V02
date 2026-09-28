import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const sourcePath = process.argv[2];
const outputDir = process.argv[3];
if (!sourcePath || !outputDir) {
  throw new Error("Usage: node build_performance_standards_by_sex.mjs <source.xlsx> <output-dir>");
}

const source = await SpreadsheetFile.importXlsx(await FileBlob.load(sourcePath));
const variants = [
  { sex: "as_hatched", sheetName: "As-Hatched (รวมเพศ)", fileName: "Arbor_Acres_Plus_As_Hatched_Performance_Standard.xlsx" },
  { sex: "male", sheetName: "Male (เพศผู้)", fileName: "Arbor_Acres_Plus_Male_Performance_Standard.xlsx" },
  { sex: "female", sheetName: "Female (เพศเมีย)", fileName: "Arbor_Acres_Plus_Female_Performance_Standard.xlsx" },
];
const headers = [["standard_id", "breed", "sex", "age_days", "body_weight_g", "daily_gain_g", "adg_g_per_day", "cumulative_feed_g", "fcr", "source", "source_version", "effective_date", "approved_by", "status", "notes"]];
const font = { name: "Arial", size: 10 };

await fs.mkdir(outputDir, { recursive: true });
for (const variant of variants) {
  const sourceRows = source.worksheets.getItem(variant.sheetName).getRange("A6:G61").values;
  const dataRows = sourceRows
    .filter((row) => Number.isInteger(Number(row[0])) && Number(row[0]) >= 1)
    .map((row) => {
      const age = Number(row[0]);
      return [
        `ARBOR_ACRES_PLUS_${variant.sex.toUpperCase()}_D${String(age).padStart(2, "0")}`,
        "Arbor Acres Plus", variant.sex, age, Number(row[1]), Number(row[2]), Number(row[3]), Number(row[5]), Number(row[6]),
        "Aviagen", "Arbor Acres Plus supplied workbook", null, null, "DRAFT",
        "Set status to APPROVED after reference review.",
      ];
    });
  if (dataRows.length !== 56) throw new Error(`${variant.sheetName} must contain daily data for days 1–56`);

  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add("Standards");
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[`Arbor Acres Plus performance standard: ${variant.sex}`]];
  sheet.getRange("A2").format = { font: { name: "Arial", size: 14, bold: true, color: "#1F2937" } };
  sheet.getRange("A3").values = [["Source: supplied Aviagen reference workbook. Review the source revision, then change status from DRAFT to APPROVED before model training or packaging."]];
  sheet.getRange("A3").format = { font: { name: "Arial", size: 10, italic: true, color: "#475569" } };
  sheet.getRange("A5:O5").values = headers;
  sheet.getRange(`A6:O${5 + dataRows.length}`).values = dataRows;
  sheet.getRange(`A5:O${5 + dataRows.length}`).format.font = font;
  sheet.getRange("A5:O5").format = { fill: "#1F4E78", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
  sheet.getRange(`A6:O${5 + dataRows.length}`).format.verticalAlignment = "center";
  sheet.getRange(`A5:O${5 + dataRows.length}`).format.borders = { preset: "outside", style: "thin", color: "#CBD5E1" };
  sheet.getRange(`D6:H${5 + dataRows.length}`).format.numberFormat = "#,##0.0";
  sheet.getRange(`I6:I${5 + dataRows.length}`).format.numberFormat = "0.000";
  sheet.getRange(`L6:L${5 + dataRows.length}`).format.numberFormat = "yyyy-mm-dd";
  sheet.getRange(`N6:N${5 + dataRows.length}`).format = { fill: "#FFF8D6", font: { name: "Arial", size: 10, bold: true, color: "#7C2D12" } };
  sheet.getRange("A:A").format.columnWidth = 34;
  sheet.getRange("B:B").format.columnWidth = 24;
  sheet.getRange("C:C").format.columnWidth = 14;
  sheet.getRange("D:I").format.columnWidth = 15;
  sheet.getRange("J:J").format.columnWidth = 14;
  sheet.getRange("K:K").format.columnWidth = 30;
  sheet.getRange("L:N").format.columnWidth = 18;
  sheet.getRange("O:O").format.columnWidth = 48;
  sheet.freezePanes.freezeRows(5);
  sheet.tables.add(`A5:O${5 + dataRows.length}`, true, `Standards_${variant.sex}`);
  workbook.recalculate();
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(path.join(outputDir, variant.fileName));
  console.log(`${variant.sex}: ${dataRows.length} rows`);
}
