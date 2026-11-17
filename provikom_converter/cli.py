"""Command-Line Interface (CLI) for Provikom Converter."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from provikom_converter.adapters.base import (
    MissingDependencyError,
    UnsupportedRuntimeError,
)
from provikom_converter.analyzer.archive import ArchiveSecurityError
from provikom_converter.orchestration.pipeline import ConverterPipeline
from provikom_converter.server import run_server
from provikom_converter.version import __version__


def format_human_summary(res) -> str:
    r = res.report
    lines = [
        "=" * 72,
        f"  PROVIKOM CONVERTER - COMPATIBILITY REPORT (v{__version__})",
        "=" * 72,
        f"  Target Archive:  {r.metadata.target_file} ({r.metadata.file_size_bytes:,} bytes)",
        f"  SHA-256:         {r.metadata.sha256[:16]}...{r.metadata.sha256[-16:]}",
        f"  Main-Class:      {r.manifest.main_class or '(none detected)'}",
        f"  Class-Path:      {' '.join(r.manifest.class_path) if r.manifest.class_path else '(none)'}",
        f"  Bytecode:        {r.class_file_info.max_java_version} (major {r.class_file_info.max_major_version})",
        f"  Inventory:       {r.archive_summary.total_classes} classes, {r.archive_summary.total_resources} resources, {r.archive_summary.total_native_libraries} native libs",
        "-" * 72,
        "  DETECTED CAPABILITIES & APIS:",
    ]

    for category, feats in r.features_detected.items():
        if feats:
            cat_label = category.replace("_", " ").upper()
            feat_names = [f["name"] for f in feats]
            lines.append(f"   * {cat_label:<20}: {', '.join(feat_names)}")

    if r.archive_summary.security_warnings:
        lines.append("-" * 72)
        lines.append("  SECURITY WARNINGS / AUDIT ALERTS:")
        for w in r.archive_summary.security_warnings:
            lines.append(f"   ! {w}")

    lines.append("-" * 72)
    lines.append("  BACKEND COMPATIBILITY EVALUATION:")
    for b_id, b in r.backend_compatibility.items():
        status_badge = b["status"].upper().replace("_", " ")
        lines.append(f"   [{status_badge:<25}] {b['backend_name']}")
        lines.append(f"      Summary: {b['summary']}")
        if b["blockers"]:
            lines.append(f"      Blockers: {'; '.join(b['blockers'])}")
        if b["workarounds_needed"]:
            lines.append(f"      Workarounds: {'; '.join(b['workarounds_needed'])}")

    lines.append("-" * 72)
    lines.append(f"  RECOMMENDATION: Primary backend -> {r.recommendation.primary_backend.upper()} (Feasibility: {r.recommendation.feasibility.upper()})")
    for t in r.recommendation.key_takeaways:
        lines.append(f"   > {t}")
    lines.append("=" * 72)
    return "\n".join(lines)


def run_analyze(args: argparse.Namespace) -> int:
    target = Path(args.jar_path)
    if not target.exists():
        print(f"Error: Target path '{target}' does not exist.", file=sys.stderr)
        return 1

    pipeline = ConverterPipeline()
    try:
        res = pipeline.analyze_jar(target)
    except ArchiveSecurityError as e:
        print(f"Security Alert: Archive rejected: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Analysis failed: {e}", file=sys.stderr)
        return 1

    if args.json:
        report_json = res.report.to_json(indent=2)
        if args.output:
            Path(args.output).write_text(report_json, encoding="utf-8")
            print(f"Report written to {args.output}")
        else:
            print(report_json)
    else:
        print(format_human_summary(res))
        if args.output:
            Path(args.output).write_text(res.report.to_json(indent=2), encoding="utf-8")
            print(f"\nJSON report saved to {args.output}")

    return 0


def run_build(args: argparse.Namespace) -> int:
    target = Path(args.jar_path)
    if not target.exists():
        print(f"Error: Target path '{target}' does not exist.", file=sys.stderr)
        return 1

    out_dir = Path(args.output)
    pipeline = ConverterPipeline()

    try:
        print(f"Building playable web artifact for '{target.name}' using '{args.backend}' backend...")
        result = pipeline.build_artifact(
            jar_path=target,
            output_dir=out_dir,
            backend=args.backend,
            game_title=args.title,
            force_overwrite=args.force,
        )
    except ArchiveSecurityError as e:
        print(f"Security Error: Untrusted archive rejected: {e}", file=sys.stderr)
        return 2
    except UnsupportedRuntimeError as e:
        print(f"Runtime Selection Error: {e}", file=sys.stderr)
        return 1
    except MissingDependencyError as e:
        print(f"Dependency Error: {e}", file=sys.stderr)
        return 1
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Build failed: {e}", file=sys.stderr)
        return 1

    print("\n" + "=" * 68)
    print("  BUILD SUCCESSFUL")
    print("=" * 68)
    print(f"  Game Title:        {result.game_title}")
    print(f"  Backend:           {result.backend_id.upper()} 5.0")
    print(f"  Runtime Target:    {result.runtime_label}")
    if result.is_experimental:
        print("  Notice:            Using an experimental preview runtime.")
    compatibility = result.metadata.get("compatibility", {})
    if compatibility.get("status"):
        print(f"  Compatibility:     {compatibility['status']} (confidence {compatibility.get('confidence_score', 'n/a')})")
    print(f"  Main Class:        {result.metadata.get('game', {}).get('main_class') or '(not detected)'}")
    print(f"  Output Directory:  {result.output_directory}")
    print(f"  Entry Point HTML:  {result.entry_html}")
    if result.staged_dependencies:
        print(f"  Dependencies ({len(result.staged_dependencies)}):")
        for d in result.staged_dependencies:
            print(f"    - {d.relative_path} -> {d.virtual_path} ({d.size_bytes:,} bytes)")
    notes = result.metadata.get("notes", [])
    if notes:
        print("-" * 68)
        print("  COMPATIBILITY NOTES:")
        for note in notes:
            print(f"    * {note}")
    print("-" * 68)
    print("  To preview the game locally, run:")
    print(f"    provikom serve {result.output_directory} --port 8080")
    print("=" * 68)
    return 0


def run_serve(args: argparse.Namespace) -> int:
    target = Path(args.directory)
    if not target.exists():
        print(f"Error: Directory '{target}' does not exist.", file=sys.stderr)
        return 1
    if not target.is_dir():
        print(f"Error: Path '{target}' is not a directory.", file=sys.stderr)
        return 1

    try:
        run_server(target, port=args.port)
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        return 1
    return 0


def run_batch(args: argparse.Namespace) -> int:
    target_dir = Path(args.target)
    if not target_dir.exists():
        print(f"Error: Path '{target_dir}' does not exist.", file=sys.stderr)
        return 1

    jars: List[Path] = []
    if target_dir.is_dir():
        jars = sorted(list(target_dir.glob("*.jar")))
    elif target_dir.suffix.lower() == ".json":
        try:
            catalog = json.loads(target_dir.read_text(encoding="utf-8"))
            base_dir = target_dir.parent.parent / "games" if (target_dir.parent.parent / "games").exists() else target_dir.parent
            for entry in catalog:
                jar_name = entry.get("jar") or entry.get("file")
                if jar_name:
                    p = base_dir / jar_name
                    if p.exists():
                        jars.append(p)
        except Exception as e:
            print(f"Failed to parse catalog JSON: {e}", file=sys.stderr)
            return 1
    elif target_dir.suffix.lower() == ".jar":
        jars = [target_dir]

    if not jars:
        print(f"No JAR files found in '{target_dir}'.", file=sys.stderr)
        return 1

    out_dir = Path(args.output_dir) if args.output_dir else Path("./reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    pipeline = ConverterPipeline()
    summaries = []

    print(f"Analyzing {len(jars)} JAR archives...")
    for j in jars:
        print(f" -> Inspecting: {j.name}")
        try:
            res = pipeline.analyze_jar(j)
            out_file = out_dir / f"{j.stem.replace(' ', '_')}.json"
            out_file.write_text(res.report.to_json(indent=2), encoding="utf-8")
            summaries.append({
                "game": j.name,
                "max_java_version": res.report.class_file_info.max_java_version,
                "classes": res.report.archive_summary.total_classes,
                "cheerpj_status": res.report.backend_compatibility["cheerpj"]["status"],
                "teavm_status": res.report.backend_compatibility["teavm"]["status"],
                "swingjs_status": res.report.backend_compatibility["swingjs"]["status"],
                "feasibility": res.report.recommendation.feasibility,
            })
        except Exception as e:
            print(f"    Failed: {e}", file=sys.stderr)

    summary_file = out_dir / "summary.json"
    summary_file.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(f"\nBatch analysis complete. {len(summaries)} reports written to '{out_dir}'.")
    return 0


def run_schema(args: argparse.Namespace) -> int:
    schema_path = Path(__file__).parent.parent / "schema" / "compatibility-report.schema.json"
    if not schema_path.exists():
        print("Schema file not found.", file=sys.stderr)
        return 1
    print(schema_path.read_text(encoding="utf-8"))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="provikom",
        description="Provikom Converter - Java Game-to-Web publishing tool.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a single JAR archive")
    analyze_parser.add_argument("jar_path", help="Path to JAR file")
    analyze_parser.add_argument("--json", action="store_true", help="Output raw JSON report")
    analyze_parser.add_argument("-o", "--output", help="Write JSON report to destination file")

    # build
    build_parser = subparsers.add_parser("build", help="Build a playable web artifact directory")
    build_parser.add_argument("jar_path", help="Path to input Java JAR archive")
    build_parser.add_argument("--backend", default="cheerpj", choices=["cheerpj"], help="Target backend compiler or runtime (default: cheerpj)")
    build_parser.add_argument("-o", "--output", required=True, help="Destination directory for generated web bundle")
    build_parser.add_argument("--title", help="Custom game title (defaults to JAR basename)")
    build_parser.add_argument("-f", "--force", action="store_true", help="Overwrite destination directory if it exists")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Serve a web artifact with HTTP Range Request support")
    serve_parser.add_argument("directory", help="Directory containing the built web artifact")
    serve_parser.add_argument("-p", "--port", type=int, default=8080, help="Port to listen on (default: 8080)")

    # batch
    batch_parser = subparsers.add_parser("batch", help="Analyze multiple JAR archives")
    batch_parser.add_argument("target", help="Directory containing JAR files or games.json catalog")
    batch_parser.add_argument("-o", "--output-dir", help="Output directory for JSON reports (default: ./reports)")

    # schema
    subparsers.add_parser("schema", help="Print compatibility report JSON Schema")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "analyze":
        return run_analyze(args)
    elif args.command == "build":
        return run_build(args)
    elif args.command == "serve":
        return run_serve(args)
    elif args.command == "batch":
        return run_batch(args)
    elif args.command == "schema":
        return run_schema(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
