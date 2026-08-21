import importlib.util
import os
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(__file__))
SCRIPT = os.path.join(ROOT, "scripts", "check_research_output.py")
SPEC = importlib.util.spec_from_file_location("check_research_output", SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class IndustryRulesTests(unittest.TestCase):
    def test_registry_has_valid_appendices_and_kpi_groups(self):
        rules = CHECKER.load_industry_rules()
        self.assertEqual(20, len(rules))
        for slug, rule in rules.items():
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rule["appendix"])), slug)
            self.assertGreaterEqual(len(rule["required_groups"]), 2, slug)
            for group in rule["required_groups"]:
                self.assertTrue(group["terms"], f"{slug}: {group['label']}")

    def test_auto_detects_primary_and_secondary_appendices(self):
        rules = CHECKER.load_industry_rules()
        text = "Industry appendix: Internet/platforms (primary) + SaaS (secondary)"
        self.assertEqual(["saas", "internet-platform"], CHECKER.detect_declared_industries(text, rules))

    def test_platform_equivalent_kpis_pass(self):
        issues = []
        text = "行业附录: internet-platform\n| 广告变现 | 分部经营利润率 |\n|---:|---:|\n| +10% | 20% |"
        CHECKER.check_industry_requirements(text, ["auto"], "report.md", issues)
        self.assertEqual([], issues)

    def test_missing_industry_kpi_is_p1(self):
        issues = []
        CHECKER.check_industry_requirements("行业附录: banks\n| NIM |\n|---:|\n| 3% |", ["auto"], "report.md", issues)
        self.assertTrue(any(issue.code == "REPORT_INDUSTRY_KPI_MISSING" and issue.severity == "P1" for issue in issues))


class LanguageTests(unittest.TestCase):
    def test_english_report_rejects_chinese_template_marker(self):
        issues = []
        CHECKER.check_language_consistency("# Acme (ACME) Equity Research Report\n本章要点：增长。", "auto", "report.md", issues)
        self.assertEqual("REPORT_LANGUAGE_MIXED", issues[0].code)

    def test_chinese_report_accepts_chinese_template_markers(self):
        issues = []
        CHECKER.check_language_consistency("# 示例（DEMO）个股投资研究报告\n本章要点：增长。", "auto", "report.md", issues)
        self.assertEqual([], issues)


class IntegratedCheckerTests(unittest.TestCase):
    def test_demo_report_passes_report_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            report, _, _ = CHECKER.write_demo_files(tmp)
            issues = []
            CHECKER.check_report(report, None, issues, ["saas"], "zh")
            self.assertEqual([], issues)


if __name__ == "__main__":
    unittest.main()
