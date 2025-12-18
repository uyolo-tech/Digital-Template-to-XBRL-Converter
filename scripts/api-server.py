#!/usr/bin/env python
"""Simple REST API for VSME Excel validation."""

import argparse
import io
import logging
import os
from pathlib import Path

from flask import Flask, jsonify, request

import mireport
from mireport.arelle.report_info import ArelleReportProcessor
from mireport.conversionresults import ConversionResultsBuilder, MessageType, Severity
from mireport.excelprocessor import VSME_DEFAULTS, ExcelProcessor

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load taxonomy on module import (required for gunicorn)
_taxonomy_loaded = False


def _ensure_taxonomy_loaded():
    global _taxonomy_loaded
    if not _taxonomy_loaded:
        logger.info("Loading taxonomy JSON...")
        mireport.loadTaxonomyJSON()
        _taxonomy_loaded = True
        logger.info("Taxonomy loaded successfully")


# Load on import for gunicorn
_ensure_taxonomy_loaded()

# Configure from environment variables
app.config["TAXONOMY_PACKAGES"] = []
app.config["WORK_OFFLINE"] = os.environ.get("WORK_OFFLINE", "false").lower() == "true"
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_FILE_SIZE", 16 * 1024 * 1024))


def validate_excel(file_stream, filename: str, skip_xbrl: bool = False) -> dict:
    """Validate an Excel file and return results as dict."""
    results_builder = ConversionResultsBuilder()

    try:
        excel = ExcelProcessor(
            file_stream,
            results_builder,
            VSME_DEFAULTS,
        )
        report = excel.populateReport()

        if not skip_xbrl and report.hasFacts:
            report_package = report.getInlineReportPackage()
            arp = ArelleReportProcessor(
                taxonomyPackages=app.config.get("TAXONOMY_PACKAGES", []),
                workOffline=app.config.get("WORK_OFFLINE", False),
            )
            arelle_results = arp.validateReportPackage(report_package)
            results_builder.addMessages(arelle_results.messages)

    except Exception as e:
        results_builder.addMessage(
            f"Exception: {e}",
            Severity.ERROR,
            MessageType.Conversion,
        )

    results = results_builder.build()

    return {
        "id": results.conversionId,
        "filename": filename,
        "success": results.conversionSuccessful,
        "xbrl_valid": results.isXbrlValid if not skip_xbrl else None,
        "overall_severity": results.getOverallSeverity().value,
        "cells_queried": results.cellsQueried,
        "cells_populated": results.cellsPopulated,
        "has_errors": results.hasErrors(),
        "has_warnings": results.hasWarnings(),
        "error_count": sum(1 for m in results.userMessages if m.severity == Severity.ERROR),
        "warning_count": sum(1 for m in results.userMessages if m.severity == Severity.WARNING),
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


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


@app.route("/validate", methods=["POST"])
def validate():
    """
    Validate an Excel file.

    Request:
        - Content-Type: multipart/form-data
        - file: The Excel file to validate
        - skip_xbrl: Optional, set to "true" to skip XBRL validation

    Response:
        JSON with validation results
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.lower().endswith(".xlsx"):
        return jsonify({"error": "Only .xlsx files are supported"}), 400

    skip_xbrl = request.form.get("skip_xbrl", "false").lower() == "true"

    file_content = file.read()
    file_stream = io.BytesIO(file_content)

    result = validate_excel(file_stream, file.filename, skip_xbrl)

    status_code = 200 if result["success"] else 422
    return jsonify(result), status_code


@app.route("/validate/path", methods=["POST"])
def validate_path():
    """
    Validate an Excel file by path (for local testing).

    Request:
        - Content-Type: application/json
        - path: Path to the Excel file
        - skip_xbrl: Optional, set to true to skip XBRL validation

    Response:
        JSON with validation results
    """
    data = request.get_json()
    if not data or "path" not in data:
        return jsonify({"error": "No path provided"}), 400

    file_path = Path(data["path"])
    if not file_path.exists():
        return jsonify({"error": f"File not found: {file_path}"}), 404

    if not file_path.suffix.lower() == ".xlsx":
        return jsonify({"error": "Only .xlsx files are supported"}), 400

    skip_xbrl = data.get("skip_xbrl", False)

    result = validate_excel(file_path, file_path.name, skip_xbrl)

    status_code = 200 if result["success"] else 422
    return jsonify(result), status_code


def main():
    parser = argparse.ArgumentParser(description="VSME Validation API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--taxonomy-packages",
        nargs="+",
        default=[],
        help="Paths to taxonomy packages for offline validation",
    )
    args = parser.parse_args()

    mireport.loadTaxonomyJSON()

    if args.taxonomy_packages:
        app.config["TAXONOMY_PACKAGES"] = [Path(p) for p in args.taxonomy_packages]
        app.config["WORK_OFFLINE"] = True
        print(f"Working offline with {len(args.taxonomy_packages)} taxonomy packages")
    else:
        app.config["TAXONOMY_PACKAGES"] = []
        app.config["WORK_OFFLINE"] = False
        print("Working online (will fetch taxonomy from web)")

    print(f"Starting API server on http://{args.host}:{args.port}")
    print("Endpoints:")
    print("  GET  /health           - Health check")
    print("  POST /validate         - Validate uploaded file (multipart/form-data)")
    print("  POST /validate/path    - Validate file by path (JSON body)")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
