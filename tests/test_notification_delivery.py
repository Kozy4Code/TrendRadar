import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def _stub_module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def load_main_module():
    class Placeholder:
        pass

    stubs = {
        "trendradar": _stub_module("trendradar", __version__="6.10.0"),
        "trendradar.context": _stub_module("trendradar.context", AppContext=Placeholder),
        "trendradar.core": _stub_module("trendradar.core", load_config=lambda: {}),
        "trendradar.core.analyzer": _stub_module(
            "trendradar.core.analyzer", convert_keyword_stats_to_platform_stats=lambda *args: []
        ),
        "trendradar.crawler": _stub_module("trendradar.crawler", DataFetcher=Placeholder),
        "trendradar.storage": _stub_module(
            "trendradar.storage", convert_crawl_results_to_news_data=lambda *args: None
        ),
        "trendradar.utils.time": _stub_module(
            "trendradar.utils.time",
            DEFAULT_TIMEZONE="Asia/Shanghai",
            is_within_days=lambda *args: True,
            calculate_days_old=lambda *args: 0,
        ),
        "trendradar.ai": _stub_module(
            "trendradar.ai", AIAnalyzer=Placeholder, AIAnalysisResult=Placeholder
        ),
        "trendradar.core.scheduler": _stub_module(
            "trendradar.core.scheduler", ResolvedSchedule=Placeholder
        ),
        "trendradar.commands": _stub_module(
            "trendradar.commands",
            check_all_versions=lambda *args: (False, None),
            run_doctor=lambda: True,
            run_test_notification=lambda config: True,
            handle_status_commands=lambda config: None,
        ),
        "trendradar.commands.version": _stub_module(
            "trendradar.commands.version",
            _fetch_remote_version=lambda *args: None,
            _parse_version=lambda value: value,
        ),
    }
    previous = {name: sys.modules.get(name) for name in stubs}
    try:
        sys.modules.update(stubs)
        spec = importlib.util.spec_from_file_location(
            "trendradar.__main__", ROOT / "trendradar" / "__main__.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop("trendradar.__main__", None)
        for name, original in previous.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class NotificationDeliveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_main_module()

    def test_any_successful_channel_satisfies_delivery_contract(self):
        self.module.ensure_notification_delivered({"wework": False, "feishu": True})

    def test_all_failed_channels_raise_delivery_error(self):
        with self.assertRaises(self.module.NotificationDeliveryError):
            self.module.ensure_notification_delivered({"wework": False})

    def test_main_exits_nonzero_when_delivery_error_reaches_entrypoint(self):
        analyzer = types.SimpleNamespace(
            is_github_actions=False,
            ctx=types.SimpleNamespace(config={"DEBUG": False}),
            run=Mock(side_effect=self.module.NotificationDeliveryError("wework")),
        )

        with (
            patch.object(self.module, "load_config", return_value={}),
            patch.object(self.module, "NewsAnalyzer", return_value=analyzer),
            patch.object(sys, "argv", ["trendradar"]),
        ):
            with self.assertRaises(SystemExit) as raised:
                self.module.main()

        self.assertEqual(raised.exception.code, 1)

    def test_run_propagates_delivery_error_to_entrypoint(self):
        analyzer = self.module.NewsAnalyzer.__new__(self.module.NewsAnalyzer)
        analyzer.ctx = types.SimpleNamespace(
            config={"DEBUG": False},
            cleanup=Mock(),
        )
        analyzer._initialize_and_check_config = Mock(return_value=True)
        analyzer._get_mode_strategy = Mock(return_value={})
        analyzer._crawl_data = Mock(return_value=({}, {}, []))
        analyzer._crawl_rss_data = Mock(return_value=(None, None, None, set()))
        analyzer._execute_mode_strategy = Mock(
            side_effect=self.module.NotificationDeliveryError("wework")
        )

        with self.assertRaises(self.module.NotificationDeliveryError):
            analyzer.run()

        analyzer.ctx.cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
