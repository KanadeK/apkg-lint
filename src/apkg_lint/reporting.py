"""Text, JSON, HTML, and SARIF reporters."""

from __future__ import annotations

import html
import json
from collections import Counter
from collections.abc import Iterable
from typing import Any

from apkg_lint import __version__
from apkg_lint.model import AuditReport, RuleDefinition, Severity
from apkg_lint.rules import RULES

OperationalError = tuple[str, str]

_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "error": "\033[31m",
    "warning": "\033[33m",
    "info": "\033[36m",
    "pass": "\033[32m",
}


def _paint(value: str, style: str, enabled: bool) -> str:
    if not enabled:
        return value
    return f"{_ANSI[style]}{value}{_ANSI['reset']}"


def _aggregate_summary(reports: Iterable[AuditReport]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for report in reports:
        counts.update(report.summary())
    return {severity.label(): counts[severity.label()] for severity in reversed(tuple(Severity))}


def render_text(
    reports: list[AuditReport],
    errors: list[OperationalError],
    *,
    color: bool,
) -> str:
    lines = [_paint(f"apkg-lint {__version__}", "bold", color)]
    for report in reports:
        summary = report.summary()
        if summary["error"]:
            status = _paint("FAIL", "error", color)
        elif summary["warning"]:
            status = _paint("WARN", "warning", color)
        else:
            status = _paint("PASS", "pass", color)
        lines.extend(
            [
                "",
                f"{status}  {report.source}",
                f"  package={report.package_version}  schema={report.schema_version}  "
                f"notes={report.counts['notes']}  cards={report.counts['cards']}  "
                f"media={report.counts['media']}",
                f"  sha256={report.sha256}",
            ]
        )
        if not report.findings:
            lines.append("  No findings.")
        for finding in report.findings:
            label = finding.severity.label().upper()
            lines.extend(
                [
                    "",
                    f"  {_paint(label, finding.severity.label(), color)} "
                    f"{finding.rule_id}  {finding.message}",
                    f"    at: {finding.location}",
                    f"    evidence: {finding.evidence}",
                    f"    fix: {finding.remediation}",
                ]
            )
    for source, message in errors:
        lines.extend(
            [
                "",
                f"{_paint('ERROR', 'error', color)}  {source}",
                f"  Could not inspect package: {message}",
            ]
        )
    summary = _aggregate_summary(reports)
    lines.extend(
        [
            "",
            f"Summary: files={len(reports)}, operational_errors={len(errors)}, "
            f"errors={summary['error']}, warnings={summary['warning']}, "
            f"info={summary['info']}",
        ]
    )
    return "\n".join(lines) + "\n"


def render_json(reports: list[AuditReport], errors: list[OperationalError]) -> str:
    payload = {
        "schema": "https://raw.githubusercontent.com/KanadeK/apkg-lint/main/"
        "schema/apkg-lint-report-v1.schema.json",
        "tool": {"name": "apkg-lint", "version": __version__},
        "summary": {
            "files": len(reports),
            "operational_errors": len(errors),
            **_aggregate_summary(reports),
        },
        "errors": [{"source": source, "message": message} for source, message in errors],
        "reports": [report.to_dict() for report in reports],
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _rule_to_sarif(rule: RuleDefinition) -> dict[str, Any]:
    return {
        "id": rule.id,
        "name": rule.title.replace(" ", ""),
        "shortDescription": {"text": rule.title},
        "fullDescription": {"text": rule.description},
        "defaultConfiguration": {
            "level": {
                Severity.ERROR: "error",
                Severity.WARNING: "warning",
                Severity.INFO: "note",
            }[rule.default_severity]
        },
    }


def render_sarif(reports: list[AuditReport], errors: list[OperationalError]) -> str:
    results: list[dict[str, Any]] = []
    for report in reports:
        for finding in report.findings:
            results.append(
                {
                    "ruleId": finding.rule_id,
                    "level": {
                        Severity.ERROR: "error",
                        Severity.WARNING: "warning",
                        Severity.INFO: "note",
                    }[finding.severity],
                    "message": {
                        "text": f"{finding.message} [{finding.location}]. {finding.remediation}"
                    },
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": report.source},
                            }
                        }
                    ],
                    "properties": {
                        "evidence": finding.evidence,
                        "apkgLocation": finding.location,
                        **finding.properties,
                    },
                }
            )
    for source, message in errors:
        results.append(
            {
                "ruleId": "APKG000",
                "level": "error",
                "message": {"text": f"Could not inspect package: {message}"},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": source}}}],
            }
        )
    rules = [
        {
            "id": "APKG000",
            "name": "PackageReadError",
            "shortDescription": {"text": "Package could not be inspected"},
        },
        *[_rule_to_sarif(rule) for rule in RULES],
    ]
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "apkg-lint",
                        "version": __version__,
                        "informationUri": "https://github.com/KanadeK/apkg-lint",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def render_html(reports: list[AuditReport], errors: list[OperationalError]) -> str:
    summary = _aggregate_summary(reports)
    report_sections: list[str] = []
    for report in reports:
        finding_rows = []
        for finding in report.findings:
            finding_rows.append(
                f"<article class='finding severity-{html.escape(finding.severity.label())}'>"
                f"<div class='finding-title'><span>{html.escape(finding.severity.label())}</span>"
                f"<code>{html.escape(finding.rule_id)}</code> {html.escape(finding.message)}</div>"
                f"<dl><dt>Location</dt><dd><code>{html.escape(finding.location)}</code></dd>"
                f"<dt>Evidence</dt><dd>{html.escape(finding.evidence)}</dd>"
                f"<dt>Repair</dt><dd>{html.escape(finding.remediation)}</dd></dl></article>"
            )
        if not finding_rows:
            finding_rows.append("<p class='clean'>No findings. This package passed.</p>")
        report_sections.append(
            "<section class='report'><header><div><p class='eyebrow'>APKG PREFLIGHT</p>"
            f"<h2>{html.escape(report.source)}</h2></div>"
            f"<div class='hash'>SHA-256<br><code>{report.sha256}</code></div></header>"
            "<div class='facts'>"
            f"<span>Format <strong>{html.escape(report.package_version)}</strong></span>"
            f"<span>Schema <strong>{report.schema_version}</strong></span>"
            f"<span>Notes <strong>{report.counts['notes']}</strong></span>"
            f"<span>Cards <strong>{report.counts['cards']}</strong></span>"
            f"<span>Media <strong>{report.counts['media']}</strong></span>"
            "</div>" + "".join(finding_rows) + "</section>"
        )
    error_sections = "".join(
        f"<article class='operational'><strong>{html.escape(source)}</strong>"
        f"<p>{html.escape(message)}</p></article>"
        for source, message in errors
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>apkg-lint report</title>
  <style>
    :root {{ color-scheme: light dark; --paper:#f5f1e8; --ink:#161616; --muted:#675f55;
      --line:#b9afa1; --red:#a72b2b; --amber:#9a6500; --blue:#135c73; --green:#246540; }}
    * {{ box-sizing:border-box }} body {{ margin:0; font:16px/1.55 ui-monospace,SFMono-Regular,
      Menlo,Consolas,monospace; background:var(--paper); color:var(--ink) }}
    main {{ width:min(1100px,calc(100% - 32px)); margin:48px auto 80px }}
    h1,h2,p {{ margin-top:0 }} h1 {{ font:800 clamp(2.4rem,8vw,6rem)/.9 system-ui,sans-serif;
      letter-spacing:-.07em; margin-bottom:18px }} .lede {{ max-width:70ch;color:var(--muted) }}
    .summary {{ display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--line);
      margin:32px 0;background:rgba(255,255,255,.35) }} .summary div {{ padding:18px;
      border-right:1px solid var(--line) }} .summary div:last-child {{ border:0 }}
    .summary strong {{ display:block;font:800 2rem/1 system-ui,sans-serif }}
    .report {{ border-top:5px solid var(--ink);padding-top:18px;margin-top:64px }}
    .report header {{ display:flex;justify-content:space-between;gap:24px;align-items:start }}
    h2 {{ font:750 2rem/1 system-ui,sans-serif;letter-spacing:-.04em }}
    .eyebrow {{ font-size:.75rem;letter-spacing:.16em;color:var(--muted);margin-bottom:8px }}
    .hash {{ max-width:48ch;text-align:right;color:var(--muted);font-size:.78rem;overflow-wrap:anywhere }}
    .facts {{ display:flex;flex-wrap:wrap;gap:8px;margin:22px 0 }}
    .facts span {{ border:1px solid var(--line);padding:7px 10px }}
    .finding {{ border-left:5px solid var(--blue);background:rgba(255,255,255,.42);
      padding:16px 18px;margin:12px 0 }} .severity-error {{ border-color:var(--red) }}
    .severity-warning {{ border-color:var(--amber) }} .finding-title span {{ text-transform:uppercase;
      font-weight:800;margin-right:10px }} .finding-title code {{ margin-right:10px }}
    dl {{ display:grid;grid-template-columns:90px 1fr;gap:5px 14px;margin:14px 0 0 }}
    dt {{ color:var(--muted) }} dd {{ margin:0;overflow-wrap:anywhere }} code {{ font:inherit }}
    .clean {{ color:var(--green);border:1px solid var(--green);padding:16px }}
    .operational {{ border:2px solid var(--red);padding:16px;margin:12px 0 }}
    footer {{ border-top:1px solid var(--line);padding-top:16px;margin-top:64px;color:var(--muted) }}
    @media(max-width:720px) {{ .summary {{ grid-template-columns:1fr 1fr }} .summary div {{ border-bottom:1px solid var(--line) }}
      .report header {{ display:block }} .hash {{ text-align:left;margin-top:16px }} dl {{ grid-template-columns:1fr }} }}
    @media(prefers-color-scheme:dark) {{ :root {{ --paper:#171715;--ink:#f2ede3;--muted:#aaa197;
      --line:#4e4942;--red:#ff7777;--amber:#ffc65c;--blue:#74c8df;--green:#79d89a }} }}
  </style>
</head>
<body><main>
  <p class="eyebrow">DETERMINISTIC · OFFLINE · READ-ONLY</p>
  <h1>Deck preflight.</h1>
  <p class="lede">Generated by apkg-lint {__version__}. No deck content left this machine.</p>
  <div class="summary">
    <div><strong>{len(reports)}</strong>files</div>
    <div><strong>{summary["error"]}</strong>errors</div>
    <div><strong>{summary["warning"]}</strong>warnings</div>
    <div><strong>{summary["info"]}</strong>info</div>
    <div><strong>{len(errors)}</strong>read failures</div>
  </div>
{error_sections}
{"".join(report_sections)}
  <footer>apkg-lint report schema v1 · output is deterministic and contains no generation timestamp.</footer>
</main></body></html>
"""


def render_rules_text(rules: tuple[RuleDefinition, ...] = RULES) -> str:
    lines = [f"apkg-lint {__version__} rules", ""]
    for rule in rules:
        lines.append(
            f"{rule.id}  {rule.default_severity.label():7}  {rule.title}\n  {rule.description}"
        )
    return "\n".join(lines) + "\n"


def render_rules_json(rules: tuple[RuleDefinition, ...] = RULES) -> str:
    payload = {
        "tool": {"name": "apkg-lint", "version": __version__},
        "rules": [
            {
                "id": rule.id,
                "default_severity": rule.default_severity.label(),
                "title": rule.title,
                "description": rule.description,
            }
            for rule in rules
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
