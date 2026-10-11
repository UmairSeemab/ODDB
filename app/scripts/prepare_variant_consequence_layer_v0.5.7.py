#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


EXPECTED_TYPES = [
    "missense variant",
    "inframe deletion",
    "frameshift variant",
    "intron variant",
    "regulatory region variant",
    "intergenic variant",
    "splice region variant",
    "splice donor variant",
    "non coding transcript exon variant",
    "3 prime UTR variant",
    "5 prime UTR variant",
    "stop gained",
    "synonymous variant",
    "TF binding site variant",
    "splice acceptor variant",
    "downstream gene variant",
    "stop lost",
    "upstream gene variant",
    "inframe insertion",
    "protein altering variant",
    "Multiple",
]


def read_tsv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path: Path, rows, fieldnames):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            delimiter="\t",
            extrasaction="ignore",
        )
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Prepare a deduplicated ODDB v1 variant consequence/link layer "
            "from the validated v0.5.6 ClinVar bridge reports."
        )
    )
    ap.add_argument(
        "--bridge-report-dir",
        default="reports/legacy_variant_clinvar_bridge_v0.5.6",
    )
    ap.add_argument(
        "--output-dir",
        default="reports/variant_consequence_layer_v0.5.7",
    )
    args = ap.parse_args()

    src = Path(args.bridge_report_dir)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    dva_yes_path = src / "safe_mapped_rows_current_dva.tsv"
    dva_no_path = src / "mapped_rows_not_in_current_dva.tsv"

    if not dva_yes_path.is_file():
        raise SystemExit(f"Missing report: {dva_yes_path}")
    if not dva_no_path.is_file():
        raise SystemExit(f"Missing report: {dva_no_path}")

    dva_yes = read_tsv(dva_yes_path)
    dva_no = read_tsv(dva_no_path)

    for r in dva_yes:
        r["_DVA_STATUS"] = "current_DVA_match"
    for r in dva_no:
        r["_DVA_STATUS"] = "not_in_current_DVA"

    resolved_rows = dva_yes + dva_no

    if not resolved_rows:
        raise SystemExit("No resolved rows found in v0.5.6 bridge reports.")

    # ------------------------------------------------------------
    # Variant -> consequence memberships.
    # ------------------------------------------------------------
    support = defaultdict(lambda: {
        "rows": [],
        "details": set(),
        "legacy_diseases": set(),
        "current_diseases": set(),
        "rsids": set(),
        "genes": set(),
        "dva_yes": 0,
        "dva_no": 0,
    })

    variant_categories = defaultdict(set)
    category_rows = Counter()
    category_variants = defaultdict(set)

    for r in resolved_rows:
        vid = (r.get("Current_VariantID") or "").strip()
        vtype = (r.get("Variant_Type") or "").strip()

        if not vid or not vtype:
            continue

        key = (vid, vtype)
        s = support[key]
        s["rows"].append((r.get("Source_Row") or "").strip())

        detail = (r.get("Variant_Detail") or "").strip()
        if detail:
            s["details"].add(detail)

        ld = (r.get("Legacy_DiseaseID") or "").strip()
        if ld:
            s["legacy_diseases"].add(ld)

        cd = (r.get("Current_DiseaseID") or "").strip()
        if cd:
            s["current_diseases"].add(cd)

        rsid = (r.get("rsID") or "").strip()
        if rsid:
            s["rsids"].add(rsid)

        gene = (r.get("Gene") or "").strip()
        if gene:
            s["genes"].add(gene)

        if r["_DVA_STATUS"] == "current_DVA_match":
            s["dva_yes"] += 1
        else:
            s["dva_no"] += 1

        variant_categories[vid].add(vtype)
        category_rows[vtype] += 1
        category_variants[vtype].add(vid)

    membership_rows = []

    for (vid, vtype), s in sorted(support.items()):
        evidence_basis = (
            "legacy_variant_identity_plus_current_DVA"
            if s["dva_yes"] > 0 and s["dva_no"] == 0
            else
            "legacy_variant_identity_mixed_DVA_context"
            if s["dva_yes"] > 0 and s["dva_no"] > 0
            else
            "legacy_variant_identity_only"
        )

        membership_rows.append({
            "Current_VariantID": vid,
            "Variant_Type": vtype,
            "Supporting_Legacy_Row_Count": len(s["rows"]),
            "Current_DVA_Matching_Row_Count": s["dva_yes"],
            "Legacy_Nonmatching_DVA_Row_Count": s["dva_no"],
            "Evidence_Basis": evidence_basis,
            "rsIDs": "|".join(sorted(s["rsids"])),
            "Legacy_DiseaseIDs": "|".join(sorted(s["legacy_diseases"])),
            "Current_DiseaseIDs": "|".join(sorted(s["current_diseases"])),
            "Legacy_Gene_Values": "|".join(sorted(s["genes"])),
            "Variant_Detail_Values": "|".join(sorted(s["details"])),
            "Source_Rows": "|".join(sorted(
                s["rows"],
                key=lambda x: int(x) if str(x).isdigit() else str(x)
            )),
            "Source": "ODDB legacy Variant_Disease_final_file.xlsx",
            "Mapping_Bridge": (
                "legacy rsID -> frozen ClinVar RS# (dbSNP) -> "
                "ClinVar VariationID -> ODDB-VAR-CV<VariationID>"
            ),
        })

    multi_category_variants = {
        vid: cats
        for vid, cats in variant_categories.items()
        if len(cats) > 1
    }

    # ------------------------------------------------------------
    # Variant external links.
    # ------------------------------------------------------------
    link_support = defaultdict(lambda: {
        "rows": set(),
        "dva_yes": 0,
        "dva_no": 0,
    })

    resource_fields = [
        ("Ensembl", "Ensembl_URL"),
        ("dbSNP", "dbSNP_URL"),
        ("gnomAD", "gnomAD_URL"),
    ]

    for r in resolved_rows:
        vid = (r.get("Current_VariantID") or "").strip()
        if not vid:
            continue

        for resource, field in resource_fields:
            url = (r.get(field) or "").strip()
            if not url:
                continue

            key = (vid, resource, url)
            link_support[key]["rows"].add(
                (r.get("Source_Row") or "").strip()
            )

            if r["_DVA_STATUS"] == "current_DVA_match":
                link_support[key]["dva_yes"] += 1
            else:
                link_support[key]["dva_no"] += 1

    link_rows = []

    for (vid, resource, url), s in sorted(link_support.items()):
        link_rows.append({
            "Current_VariantID": vid,
            "Resource": resource,
            "URL": url,
            "Supporting_Legacy_Row_Count": len(s["rows"]),
            "Current_DVA_Matching_Row_Count": s["dva_yes"],
            "Legacy_Nonmatching_DVA_Row_Count": s["dva_no"],
            "Source_Rows": "|".join(sorted(
                s["rows"],
                key=lambda x: int(x) if str(x).isdigit() else str(x)
            )),
            "Source": "ODDB legacy Variant_Disease_final_file.xlsx",
        })

    # ------------------------------------------------------------
    # Category summary.
    # ------------------------------------------------------------
    category_summary = []
    observed_membership_types = {r["Variant_Type"] for r in membership_rows}

    for i, vtype in enumerate(EXPECTED_TYPES, start=1):
        category_summary.append({
            "Display_Order": i,
            "Variant_Type": vtype,
            "Resolved_Legacy_Row_Count": category_rows[vtype],
            "Unique_Current_Variants": len(category_variants[vtype]),
            "Has_Membership": "yes" if vtype in observed_membership_types else "no",
        })

    unexpected = sorted(observed_membership_types - set(EXPECTED_TYPES))
    missing = sorted(set(EXPECTED_TYPES) - observed_membership_types)

    # ------------------------------------------------------------
    # Reports.
    # ------------------------------------------------------------
    write_tsv(
        out / "variant_consequence_memberships.tsv",
        membership_rows,
        [
            "Current_VariantID",
            "Variant_Type",
            "Supporting_Legacy_Row_Count",
            "Current_DVA_Matching_Row_Count",
            "Legacy_Nonmatching_DVA_Row_Count",
            "Evidence_Basis",
            "rsIDs",
            "Legacy_DiseaseIDs",
            "Current_DiseaseIDs",
            "Legacy_Gene_Values",
            "Variant_Detail_Values",
            "Source_Rows",
            "Source",
            "Mapping_Bridge",
        ],
    )

    write_tsv(
        out / "variant_external_links.tsv",
        link_rows,
        [
            "Current_VariantID",
            "Resource",
            "URL",
            "Supporting_Legacy_Row_Count",
            "Current_DVA_Matching_Row_Count",
            "Legacy_Nonmatching_DVA_Row_Count",
            "Source_Rows",
            "Source",
        ],
    )

    write_tsv(
        out / "variant_consequence_category_summary.tsv",
        category_summary,
        [
            "Display_Order",
            "Variant_Type",
            "Resolved_Legacy_Row_Count",
            "Unique_Current_Variants",
            "Has_Membership",
        ],
    )

    multi_rows = []
    for vid, cats in sorted(multi_category_variants.items()):
        multi_rows.append({
            "Current_VariantID": vid,
            "Category_Count": len(cats),
            "Variant_Types": "|".join(sorted(cats)),
        })

    write_tsv(
        out / "variants_with_multiple_consequence_categories.tsv",
        multi_rows,
        [
            "Current_VariantID",
            "Category_Count",
            "Variant_Types",
        ],
    )

    summary = {
        "version": "v0.5.7",
        "input_current_DVA_rows": len(dva_yes),
        "input_nonmatching_DVA_rows": len(dva_no),
        "resolved_legacy_rows_total": len(resolved_rows),
        "unique_current_variants_with_consequence": len(variant_categories),
        "unique_variant_consequence_memberships": len(membership_rows),
        "variants_with_multiple_consequence_categories":
            len(multi_category_variants),
        "external_link_rows": len(link_rows),
        "variant_types_expected": len(EXPECTED_TYPES),
        "variant_types_with_resolved_memberships":
            len(observed_membership_types),
        "missing_expected_types_after_resolved_mapping": missing,
        "unexpected_types": unexpected,
        "semantics": [
            "variant consequence is treated as a property of the resolved canonical variant",
            "legacy nonmatching disease-variant rows do not create new canonical DVA assertions",
            "DVA status is retained only as provenance for the source row",
            "Ensembl/dbSNP/gnomAD URLs are variant-level links",
            "DOI strings are not promoted to variant-level publication assertions in this step",
        ],
    }

    with (out / "variant_consequence_layer_summary.json").open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("ODDB v1 VARIANT CONSEQUENCE LAYER PREPARATION v0.5.7")
    print("=" * 88)
    print(f"Resolved legacy rows with current DVA match: {len(dva_yes):,}")
    print(f"Resolved legacy rows without current DVA match: {len(dva_no):,}")
    print(f"Resolved legacy rows total: {len(resolved_rows):,}")
    print(f"Unique current variants with consequence: {len(variant_categories):,}")
    print(f"Unique variant/consequence memberships: {len(membership_rows):,}")
    print(
        "Variants with >1 consequence category: "
        f"{len(multi_category_variants):,}"
    )
    print(f"Unique variant external-link rows: {len(link_rows):,}")

    print("\nResolved consequence coverage:")
    for r in category_summary:
        print(
            f"{r['Variant_Type']:<42s} "
            f"rows={r['Resolved_Legacy_Row_Count']:5d} "
            f"variants={r['Unique_Current_Variants']:5d}"
        )

    print("\nExpected category check:")
    print(f"Missing expected types after resolved mapping: {missing or 'none'}")
    print(f"Unexpected types: {unexpected or 'none'}")

    print("\nReports:")
    for name in [
        "variant_consequence_memberships.tsv",
        "variant_external_links.tsv",
        "variant_consequence_category_summary.tsv",
        "variants_with_multiple_consequence_categories.tsv",
        "variant_consequence_layer_summary.json",
    ]:
        print(out / name)

    print(
        "\nREAD-ONLY: MySQL, canonical DVA, frozen releases, and source files "
        "were not modified."
    )


if __name__ == "__main__":
    main()
