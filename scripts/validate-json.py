#!/usr/bin/env python
"""Validate an Excel file and output results as JSON."""

import argparse
import json
import sys
from pathlib import Path

import mireport
from mireport.arelle.report_info import ArelleReportProcessor
from mireport.conversionresults import ConversionResultsBuilder, Severity
from mireport.excelprocessor import VSME_DEFAULTS, ExcelProcessor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Excel VSME template and output results as JSON"
    )
    parser.add_argument("excel_file", type=Path, help="Path to the Excel file")
    parser.add_argument(
        "--skip-xbrl-validation",
        action="store_true",
        help="Skip XBRL validation (only check Excel parsing)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    mireport.loadTaxonomyJSON()

    results_builder = ConversionResultsBuilder()

    try:
        excel = ExcelProcessor(
            args.excel_file,
            results_builder,
            VSME_DEFAULTS,
        )
        report = excel.populateReport()

        if not args.skip_xbrl_validation and report.hasFacts:
            report_package = report.getInlineReportPackage()
            arp = ArelleReportProcessor(taxonomyPackages=[], workOffline=False)
            arelle_results = arp.validateReportPackage(report_package)
            results_builder.addMessages(arelle_results.messages)

    except Exception as e:
        results_builder.addMessage(
            f"Exception: {e}",
            Severity.ERROR,
            mireport.conversionresults.MessageType.Conversion,
        )

    results = results_builder.build()

    output = {
        "id": results.conversionId,
        "success": results.conversionSuccessful,
        "xbrl_valid": results.isXbrlValid if not args.skip_xbrl_validation else None,
        "overall_severity": results.getOverallSeverity().value,
        "cells_queried": results.cellsQueried,
        "cells_populated": results.cellsPopulated,
        "has_errors": results.hasErrors(),
        "has_warnings": results.hasWarnings(),
        "messages": [
            {
                "text": m.messageText,
                "severity": m.severity.value,
                "type": m.messageType.value,
                "concept": m.conceptQName,
                "excel_ref": m.excelReference,
            }
            for m in results.userMessages
        ],
    }

    if args.pretty:
        print(json.dumps(output, indent=2))
    else:
        print(json.dumps(output))

    sys.exit(0 if results.conversionSuccessful and not results.hasErrors() else 1)


if __name__ == "__main__":
    main()
